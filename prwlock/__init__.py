# -*- coding: utf-8 -*-

import platform

__version__ = '0.3.0'

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
class ReaderLock(object):
    def __init__(self, lock, timeout=None):
        self.lock = lock
        self.timeout = timeout

    def __enter__(self):
        self.lock.acquire_read(timeout=self.timeout)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()

class WriterLock(object):
    def __init__(self, lock, timeout=None):
        self.lock = lock
        self.timeout = timeout

    def __enter__(self):
        self.lock.acquire_write(timeout=self.timeout)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()

def reader_lock(self, timeout=None):
    return ReaderLock(self, timeout=timeout)

def writer_lock(self, timeout=None):
    return WriterLock(self, timeout=None)


RWLock.reader_lock = reader_lock
RWLock.writer_lock = writer_lock

__all__.append('RWLock')
