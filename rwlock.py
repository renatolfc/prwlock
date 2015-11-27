#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os        # For strerror
import mmap      # For setting up a shared memory region
import ctypes    # For doing the actual wrapping of librt & rwlock
import platform  # To figure which architecture we're running in

from ctypes.util import find_library

# Loads the library in which the functions we're wrapping are defined
librt = ctypes.CDLL(find_library('rt'), use_errno=True)

if platform.system() == 'Linux':
    if platform.architecture()[0] == '64bit':
        pthread_rwlock_t = ctypes.c_byte * 56
    elif platform.architecture()[0] == '32bit':
        pthread_rwlock_t = ctypes.c_byte * 32
    else:
        pthread_rwlock_t = ctypes.c_byte * 44
else:
    raise Exception("Unsupported operating system.")

pthread_rwlockattr_t = ctypes.c_byte * 8

PTHREAD_PROCESS_SHARED = 1

pthread_rwlockattr_t_p = ctypes.POINTER(pthread_rwlockattr_t)
pthread_rwlock_t_p = ctypes.POINTER(pthread_rwlock_t)

API = [
    ('pthread_rwlock_destroy', [pthread_rwlock_t_p]),
    ('pthread_rwlock_init', [pthread_rwlock_t_p, pthread_rwlockattr_t_p]),
    ('pthread_rwlock_unlock', [pthread_rwlock_t_p]),
    ('pthread_rwlock_wrlock', [pthread_rwlock_t_p]),
    ('pthread_rwlockattr_destroy', [pthread_rwlockattr_t_p]),
    ('pthread_rwlockattr_init', [pthread_rwlockattr_t_p]),
    ('pthread_rwlockattr_setpshared', [pthread_rwlockattr_t_p, ctypes.c_int]),
]


def error_check(result, func, arguments):
    name = func.__name__
    if result != 0:
        error = os.strerror(ctypes.get_errno())
        raise OSError(result, '{} failed {}'.format(name, error))


def augment_function(library, name, argtypes):
    function = getattr(library, name)
    function.argtypes = argtypes
    function.errcheck = error_check

# At the global level we add argument types and error checking to the
# functions:
for function, argtypes in API:
    augment_function(librt, function, argtypes)


class RWLock(object):
    def __init__(self):
        try:
            # Define these guards so we know which attribution has failed
            buf, lock, lockattr = None, None, None

            # mmap allocates page sized chunks, and the data structures we
            # use are smaller than a page. Therefore, we request a whole
            # page
            buf = mmap.mmap(-1, mmap.PAGESIZE, mmap.MAP_SHARED)

            # Use the memory we just obtained from mmap and obtain pointers
            # to that data
            offset = ctypes.sizeof(pthread_rwlock_t)
            tmplock = pthread_rwlock_t.from_buffer(buf)
            lock_p = ctypes.byref(tmplock)
            tmplockattr = pthread_rwlockattr_t.from_buffer(buf, offset)
            lockattr_p = ctypes.byref(tmplockattr)

            # Initialize the rwlock attributes and make it process shared
            librt.pthread_rwlockattr_init(lockattr_p)
            lockattr = tmplockattr
            librt.pthread_rwlockattr_setpshared(lockattr_p,
                                                PTHREAD_PROCESS_SHARED)

            # Initialize the rwlock
            librt.pthread_rwlock_init(lock_p, lockattr_p)
            lock = tmplock

            # Finally initialize this instance's members
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

    def acquire_read(self):
        librt.pthread_rwlock_rdlock(self._lock_p)

    def acquire_write(self):
        librt.pthread_rwlock_wrlock(self._lock_p)

    def release(self):
        librt.pthread_rwlock_unlock(self._lock_p)

    def __del__(self):
        librt.pthread_rwlockattr_destroy(self._lockattr_p)
        self._lockattr, self._lockattr_p = None, None
        librt.pthread_rwlock_destroy(self._lock_p)
        self._lock, self._lock_p = None, None
        self._buf.close()
