# -*- coding: utf-8 -*-

import platform

__version__ = '0.4.0'

# Note: names are added to __all__ depending on what system we're on
__all__ = []

if platform.system() == 'Windows':
    from wrwlock import RWLockWindows as RWLock
else:
    from . import prwlock as _prwlock

    def set_pthread_process_shared(n_process):
        """
        Sets the value of the PTHREAD_PROCESS_SHARED constant
        :param n_process: number of processes
        """
        _prwlock.PTHREAD_PROCESS_SHARED = n_process

    def get_pthread_process_shared():
        """
        Returns the value of the PTHREAD_PROCESS_SHARED constant
        """
        return _prwlock.PTHREAD_PROCESS_SHARED

    __all__.append('set_pthread_process_shared')
    __all__.append('get_pthread_process_shared')

    if platform.system() == 'Darwin':
        RWLock = _prwlock.RWLockOSX
    else:
        # Uses the default posix implementation
        RWLock = _prwlock.RWLockPosix

# Monkey patch resolved RWLock class to implement __enter__ and __exit__
class GenericLockContextManager(object):
    def __init__(self, lock, method, timeout=None):
        self.lock = lock
        self.locked = False
        self.method = method
        self.timeout = timeout
        if method not in ['read', 'write']:
            raise ValueError('GenericLock called with invalid method %s'
                             % self.method)

    def __enter__(self):
        locker = getattr(self.lock, 'acquire_' + self.method)
        self.locked = locker(timeout=self.timeout)
        if not self.locked:
            # We have to return from the __enter__ method, but we failed to
            # acquire the lock. The only thing we can do is to fail
            raise ValueError('Unable to acquire lock in context manager')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.locked:
            self.lock.release()
        self.locked = False

def reader_lock(self, timeout=None):
    return GenericLockContextManager(self, 'read', timeout=timeout)

def writer_lock(self, timeout=None):
    return GenericLockContextManager(self, 'write', timeout=timeout)


RWLock.reader_lock = reader_lock
RWLock.writer_lock = writer_lock

__all__.append('RWLock')
