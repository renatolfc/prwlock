#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os        # For strerror
import mmap      # For setting up a shared memory region
import ctypes    # For doing the actual wrapping of librt & rwlock
import platform  # To figure which architecture we're running in
import tempfile  # To open a file to back our mmap
import errno     # To interpret errors of pthread-method calls

from time import sleep  # Used by loop based acquire-lock timeouts
from ctypes.util import find_library

if platform.system() == 'Darwin':
    librt = ctypes.CDLL(find_library('c'), use_errno=True)
    PTHREAD_PROCESS_SHARED = 1
    pthread_rwlock_t = ctypes.c_byte * 200
    pthread_rwlockattr_t = ctypes.c_byte * 24
else:
    # Loads the library in which the functions we're wrapping are defined
    librt = ctypes.CDLL(find_library('rt'), use_errno=True)
    pthread_rwlockattr_t = ctypes.c_byte * 8
    if platform.system() == 'Linux':
        PTHREAD_PROCESS_SHARED = 1
        if platform.architecture()[0] == '64bit':
            pthread_rwlock_t = ctypes.c_byte * 56
        elif platform.architecture()[0] == '32bit':
            pthread_rwlock_t = ctypes.c_byte * 32
        else:
            pthread_rwlock_t = ctypes.c_byte * 44
    elif platform.system() == 'FreeBSD':
        PTHREAD_PROCESS_SHARED = 0
        pthread_rwlock_t = ctypes.c_byte * 8
    elif platform.system() == 'OpenBSD':
        PTHREAD_PROCESS_SHARED = 0
        pthread_rwlock_t = ctypes.c_byte * 8
    elif platform.system().lower().startswith('cygwin'):
        PTHREAD_PROCESS_SHARED = 0
        pthread_rwlock_t = ctypes.c_byte * 8
    else:
        raise Exception("Unsupported operating system.")

pthread_rwlockattr_t_p = ctypes.POINTER(pthread_rwlockattr_t)
pthread_rwlock_t_p = ctypes.POINTER(pthread_rwlock_t)
timespec_t_p = ctypes.c_void_p
time_t = ctypes.c_long      # C's time_t type
SHORT_SLEEP = 0.1           # Short sleep in seconds for loop-based timeout methods


def default_error_check(result, func, arguments):
    name = func.__name__
    if result != 0:
        error = os.strerror(result)
        raise OSError(result, '{} failed {}'.format(name, error))
    return arguments

API = [
    ('pthread_rwlock_destroy', [pthread_rwlock_t_p], default_error_check),
    ('pthread_rwlock_init', [pthread_rwlock_t_p, pthread_rwlockattr_t_p], default_error_check),
    ('pthread_rwlock_unlock', [pthread_rwlock_t_p], default_error_check),
    ('pthread_rwlock_wrlock', [pthread_rwlock_t_p], default_error_check),
    # The normal callback-based error checking traps the GIL into
    # possible deadlocks under Mac OS X. Hence, avoid default error checking for
    # pthread_rwlock_tryrdlock and pthread_rwlock_trywrlock
    ('pthread_rwlock_tryrdlock', [pthread_rwlock_t_p], None),
    ('pthread_rwlock_trywrlock', [pthread_rwlock_t_p], None),
    ('pthread_rwlockattr_destroy', [pthread_rwlockattr_t_p], default_error_check),
    ('pthread_rwlockattr_init', [pthread_rwlockattr_t_p], default_error_check),
    ('pthread_rwlockattr_setpshared', [pthread_rwlockattr_t_p, ctypes.c_int], default_error_check),
]

# Implementation of timed versions of pthread_rwlock_XXlock are optional
# according to UNIX documentation. Some OSes do not implement it,
# including Mac OS X. Hence, test if it is supported
if hasattr(librt, 'pthread_rwlock_timedrdlock'):
    API.append(('pthread_rwlock_timedrdlock', [pthread_rwlock_t_p, timespec_t_p], None))
    API.append(('pthread_rwlock_timedwrlock', [pthread_rwlock_t_p, timespec_t_p], None))


def augment_function(library, name, argtypes, error_check=None):
    function = getattr(library, name)
    function.argtypes = argtypes
    if error_check:
        function.errcheck = error_check


# At the global level we add argument types and error checking to the functions:
for function, argtypes, error_check in API:
    augment_function(librt, function, argtypes, error_check)


# timespec struct from <time.h>
class TimeSpec(ctypes.Structure):
    _fields_ = [
        ("tv_sec", time_t),
        ("tv_nsec", ctypes.c_long) ]


# Create timespec from seconds
def get_timespec(seconds):
    ts = TimeSpec(librt.time(None))
    ts.tv_sec += int(seconds)
    ts.tv_nsec += int((seconds - int(seconds)) * 1e+9)
    return ts


class RWLockPosix(object):
    def __init__(self):
        self.__setup(None)
        # Note we don't have to lock accesses to self.nlocks, since RWLocks are
        # supposed to be used only for coordinating multiple *processes*. In
        # which case each process will have its own private copy of the RWLock.
        self.nlocks = 0
        self.pid = os.getpid()

        # Create links to methods that acquire locks considering timeouts
        if hasattr(librt, 'pthread_rwlock_timedrdlock'):
            self._timed_wrlock = self._pthread_timedwrlock
            self._timed_rdlock = self._pthread_timedrdlock
        else:
            self._timed_wrlock = self._loop_timedwrlock
            self._timed_rdlock = self._loop_timedrdlock

    def __setup(self, _fd=None):
        try:
            # Define these guards so we know which attribution has failed
            buf, lock, lockattr, fd = None, None, None, None

            if _fd:
                # We're being called from __setstate__, all we have to do is
                # load the file descriptor of the backing file
                fd = _fd
            else:
                # Create a temporary file with an actual file descriptor, so
                # that child processes can receive the lock via apply from the
                # multiprocessing module
                fd, name = tempfile.mkstemp()
                os.write(fd, b'\0' * mmap.PAGESIZE)

            # mmap allocates page sized chunks, and the data structures we
            # use are smaller than a page. Therefore, we request a whole
            # page
            buf = mmap.mmap(fd, mmap.PAGESIZE, mmap.MAP_SHARED)
            if _fd:
                buf.seek(0)

            # Use the memory we just obtained from mmap and obtain pointers
            # to that data
            offset = ctypes.sizeof(pthread_rwlock_t)
            tmplock = pthread_rwlock_t.from_buffer(buf)
            lock_p = ctypes.byref(tmplock)
            tmplockattr = pthread_rwlockattr_t.from_buffer(buf, offset)
            lockattr_p = ctypes.byref(tmplockattr)

            if _fd is None:
                # Initialize the rwlock attributes and make it process shared
                librt.pthread_rwlockattr_init(lockattr_p)
                lockattr = tmplockattr
                librt.pthread_rwlockattr_setpshared(lockattr_p,
                                                    PTHREAD_PROCESS_SHARED)

                # Initialize the rwlock
                librt.pthread_rwlock_init(lock_p, lockattr_p)
                lock = tmplock
            else:
                # The data is already initialized in the mmap. We only have to
                # point to it
                lockattr = tmplockattr
                lock = tmplock

            # Finally initialize this instance's members
            self._fd = fd
            self._buf = buf
            self._lock = lock
            self._lock_p = lock_p
            self._lockattr = lockattr
            self._lockattr_p = lockattr_p
        except:
            if lock:
                try:
                    librt.pthread_rwlock_destroy(lock_p)
                    lock_p, lock = None, None
                except:
                    # We really need this reference gone to free the buffer
                    lock_p, lock = None, None
            if lockattr:
                try:
                    librt.pthread_rwlockattr_destroy(lockattr_p)
                    lockattr_p, lockattr = None, None
                except:
                    # We really need this reference gone to free the buffer
                    lockattr_p, lockattr = None, None
            if buf:
                try:
                    buf.close()
                except:
                    pass
            if fd:
                try:
                    os.close(fd)
                except:
                    pass
            raise

    def _pthread_timedrdlock(self, seconds):
        ts = get_timespec(seconds)
        if librt.pthread_rwlock_timedrdlock(self._lock_p, ctypes.byref(ts)) == errno.ETIMEDOUT:
            return False
        return True

    def _pthread_timedwrlock(self, seconds):
        ts = get_timespec(seconds)
        if librt.pthread_rwlock_timedwrlock(self._lock_p, ctypes.byref(ts)) == errno.ETIMEDOUT:
            return False
        return True

    def _loop_timedrdlock(self, seconds):
        while seconds > 0.0:
            if librt.pthread_rwlock_tryrdlock(self._lock_p) == 0:
                return True
            sleep(min(SHORT_SLEEP, seconds))
            seconds -= SHORT_SLEEP
        return False

    def _loop_timedwrlock(self, seconds):
        while seconds > 0.0:
            if librt.pthread_rwlock_trywrlock(self._lock_p) == 0:
                return True
            sleep(min(SHORT_SLEEP, seconds))
            seconds -= SHORT_SLEEP
        return False

    def acquire_read(self, timeout=None):
        """acquire_read([timeout=None])

        Request a read lock, returning True if the lock is acquired;
        False otherwise. If provided, *timeout* specifies the number of
        seconds to wait for the lock before cancelling and returning False.
        """
        if timeout is None:
            librt.pthread_rwlock_rdlock(self._lock_p)
        elif not self._timed_rdlock(timeout):
            return False
        self.nlocks += 1
        return True

    def acquire_write(self, timeout=None):
        """acquire_write([timeout=None])

        Request a write lock, returning True if the lock is acquired;
        False otherwise. If provided, *timeout* specifies the number of
        seconds to wait for the lock before cancelling and returning False.
        """
        if timeout is None:
            librt.pthread_rwlock_wrlock(self._lock_p)
        elif not self._timed_wrlock(timeout):
            return False
        self.nlocks += 1
        return True

    def try_acquire_read(self):
        """Try to obtain a read lock, immediately returning True if
        the lock is acquired; False otherwise.
        """
        if librt.pthread_rwlock_tryrdlock(self._lock_p) == 0:
            self.nlocks += 1
            return True
        else:
            return False

    def try_acquire_write(self):
        """Try to obtain a write lock, returning True immediately if
        the lock can be acquired; False otherwise.
        """
        if librt.pthread_rwlock_trywrlock(self._lock_p) == 0:
            self.nlocks += 1
            return True
        else:
            return False

    def release(self):
        """Release a previously acquired read/write lock.
        """
        if self.nlocks == 0:
            raise ValueError(
                'Tried to release a released lock'
            )
        librt.pthread_rwlock_unlock(self._lock_p)
        self.nlocks -= 1

    def __getstate__(self):
        return {
                '_fd': self._fd,
                'pid': self.pid,
                'nlocks': self.nlocks,
                }

    def __setstate__(self, state):
        self.__setup(state['_fd'])
        self.pid = os.getpid()
        if self.pid == state['pid']:
            self.nlocks = state['nlocks']
        else:
            self.nlocks = 0

    def _del_lockattr(self):
        librt.pthread_rwlockattr_destroy(self._lockattr_p)
        self._lockattr, self._lockattr_p = None, None

    def _del_lock(self):
        for i in range(self.nlocks):
            self.release()

        librt.pthread_rwlock_destroy(self._lock_p)
        self._lock, self._lock_p = None, None

    def _del_buf(self):
        self._buf.close()
        self._buf = None

    def __del__(self):
        for name in '_lockattr _lock _buf'.split():
            attr = getattr(self, name, None)
            if attr is not None:
                func = getattr(self, '_del{}'.format(name))
                func()
        try:
            if hasattr(self, '_fd'):
                os.close(self._fd)
        except OSError:
            # Nothing we can do. We opened the file descriptor, we have to
            # close it. If we can't, all bets are off.
            pass


# A call to pthread_rwlock_destroy on Mac OS X raises an exception
# when providing a pointer to a pthread_rwlock_t that has already been
# destroyed. The pthread_rwlock_t struct under OS X maintains a
# signature that defines whether the lock is initialized or destroyed:
# struct _opaque_pthread_rwlock_t {
#        long __sig;
#        char __opaque[__PTHREAD_RWLOCK_SIZE__];
# };
# Hence, we must test whether the __sig of a rwlock is not set
# to zero before attempting to destroy it.
class RWLockOSX(RWLockPosix):

    def _del_lock(self):
        # Under Mac OS X, it must check whether the lock's is initialized
        if self._lock[0] != 0:
            RWLockPosix._del_lock(self)
