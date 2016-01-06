# -*- coding: utf-8 -*-
__version__ = '0.1.1'

# Note: names are added to __all__ depending on what system we're on
__all__ = []

import platform as _platform  # To figure which architecture we're running in

if _platform.system() == 'Windows':
    from wrwlock import RWLockWindows as RWLock
else:
    import prwlock as _prwlock

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

    if _platform.system() == 'Darwin':
        RWLock = _prwlock.RWLockOSX
    else:
        # Uses the default posix implementation
        RWLock = _prwlock.RWLockPosix

__all__.append('RWLock')