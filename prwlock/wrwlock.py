#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os        # For strerror
import mmap      # For setting up a shared memory region
import ctypes    # For doing the actual wrapping of librt & rwlock
import platform  # To figure which architecture we're running in

if platform.system() is not 'Windows':
    raise Exception("Unsupported operating system.")

from ctypes import windll, wintypes, Structure
k32 = windll.kernel32

# Augment the Win32 functions we need
API_W32 = [
    ('CreateMutexA', [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCSTR], wintypes.HANDLE),
    ('WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
    ('ReleaseMutex', [wintypes.HANDLE], wintypes.BOOL),
    ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL)
]

def augment_function(library, name, argtypes, restype):
    function = getattr(library, name)
    function.argtypes = argtypes
    function.restype = restype

for function, argtypes, restype in API_W32:
    augment_function(k32, function, argtypes, restype)

INFINITE = 0xFFFFFFFF

# By default, mutexes are not inherited when a new process is created.
# We need to provide security attributes that allow the mutexes to be
# shared by the synchronized processes. For more detail, see:
# https://msdn.microsoft.com/en-us/library/windows/desktop/aa379560(v=vs.85).aspx
class _SECURITY_ATTRIBUTES(Structure):
    _fields_= [("nLength", wintypes.DWORD),
               ("lpSecurityDescriptor", wintypes.LPVOID),
               ("bInheritHandle", wintypes.BOOL)]

class RWLockWindows(object):
    def __init__(self):
        self.__setup()
        self.pid = os.getpid()

    def __setup(self, _mtag=None):
        try:
            # Define these guards so we know which attribution has failed
            buf, wr_mutex, rd_mutex, mtag = None, None, None, None

            if _mtag:
                # We're being called from __setstate__, all we have to do is
                # load the memory tag for the windows shared memory
                mtag = _mtag
            else:
                mtag = "rwlock-%d" % os.getpid()

            # File descriptors are not shared across processes on Windows,
            # but an alternative is to use named shared memory:
            # https://msdn.microsoft.com/en-us/library/windows/desktop/aa366551(v=vs.85).aspx
            # Setting the underlying mmap fd to 0, will force it to use named
            # shared memory accessible via the provided memory tag.
            # Also, mmap allocates page sized chunks, and the data structures we
            # use are smaller than a page. Therefore, we request a whole page
            buf = mmap.mmap(0, mmap.PAGESIZE, mtag)

            if _mtag:
                buf.seek(0)

            # Use the memory obtained from mmap and use it as shared buffer
            # for the ctypes variables shared by the synchronized processes
            wr_mutex = wintypes.HANDLE.from_buffer(buf)
            offset = ctypes.sizeof(wintypes.HANDLE)
            rd_mutex = wintypes.HANDLE.from_buffer(buf, offset)
            offset += offset

            # Number of readers and the flag that indicates whether readers
            # are blocked must be shared by processes
            readers_blocked = ctypes.c_bool.from_buffer(buf, offset)
            offset += ctypes.sizeof(ctypes.c_bool)
            n_readers = ctypes.c_int.from_buffer(buf, offset)

            if _mtag is None:
                sa = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
                rd_mutex.value = k32.CreateMutexA(ctypes.byref(sa), False, "mt-rd-%d" % os.getpid())
                wr_mutex.value = k32.CreateMutexA(ctypes.byref(sa), False, "mt-wr-%d" % os.getpid())
                readers_blocked.value = False
                n_readers.value = 0

            # Finally initialize this instance's members
            self._buf = buf
            self._rd_mutex = rd_mutex
            self._wr_mutex = wr_mutex
            self._mtag = mtag
            self._readers_blocked = readers_blocked
            self._n_readers = n_readers
        except:
            if rd_mutex:
                k32.CloseHandle(rd_mutex.value)
            if wr_mutex:
                k32.CloseHandle(wr_mutex.value)
            if buf:
                try:
                    buf.close()
                except:
                    pass
            raise

    def acquire_read(self):
        while True:
            k32.WaitForSingleObject(self._rd_mutex.value, INFINITE)
            if not self._readers_blocked.value:
                self._n_readers.value += 1
                k32.ReleaseMutex(self._rd_mutex.value)
                return
            k32.ReleaseMutex(self._rd_mutex.value)

    def release_read(self):
        k32.WaitForSingleObject(self._rd_mutex.value, INFINITE)
        if self._n_readers.value == 0:
            raise ValueError(
                'Tried to release a released lock'
            )
        self._n_readers.value -= 1
        k32.ReleaseMutex(self._rd_mutex.value)

    def _wait_readers(self):
        # block new readers
        k32.WaitForSingleObject(self._rd_mutex.value, INFINITE)
        self._readers_blocked.value = True
        k32.ReleaseMutex(self._rd_mutex.value)

        # Wait until active readers complete
        while True:
            k32.WaitForSingleObject(self._rd_mutex.value, INFINITE)
            if self._n_readers.value == 0:
                k32.ReleaseMutex(self._rd_mutex.value)
                break
            k32.ReleaseMutex(self._rd_mutex.value)

    def acquire_write(self):
        k32.WaitForSingleObject(self._wr_mutex.value, INFINITE)
        self._wait_readers()

    def release_write(self):
        k32.WaitForSingleObject(self._rd_mutex.value, INFINITE)
        self._readers_blocked.value = False
        k32.ReleaseMutex(self._rd_mutex.value)
        k32.ReleaseMutex(self._wr_mutex.value)

    def __getstate__(self):
        return {'_mtag': self._mtag, 'pid': self.pid}

    def __setstate__(self, state):
        self.__setup(state['_mtag'])
        self.pid = os.getpid()

    def _del_lock(self):
        # TODO: Need to test when to get rid of the handles
        # Windows will delete them when the process that created
        # the mutexes completes, but I guess we can do better
        # k32.CloseHandle(self._rd_mutex.value)
        # k32.CloseHandle(self._wr_mutex.value)
        self._rd_mutex, self._wr_mutex = None
        pass

    def _del_buf(self):
        self._buf.close()
        self._buf = None

    def __del__(self):
        for name in '_lock _buf'.split():
            attr = getattr(self, name, None)
            if attr is not None:
                func = getattr(self, '_del{}'.format(name))
                func()
