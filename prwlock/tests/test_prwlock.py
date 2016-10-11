from __future__ import print_function

import os
import mmap
import time
import pickle
import unittest

import prwlock
from multiprocessing import Pool
import multiprocessing as mp


OLD_PTHREAD_PROCESS_SHARED = prwlock.get_pthread_process_shared()


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.rwlock = prwlock.RWLock()

    def tearDown(self):
        prwlock.set_pthread_process_shared(OLD_PTHREAD_PROCESS_SHARED)


class RWLockTestCase(BaseTestCase):

    def allocate_infinitely(self):
        def gen():
            while True:
                yield prwlock.RWLock()
        return [r for r in gen()]

    def test_double_release(self):
        with self.assertRaises(ValueError):
            self.rwlock.release()

    def test_simple_deadlock(self):
        with self.assertRaises(OSError):
            self.rwlock.acquire_write()
            self.rwlock.acquire_write()

    def test_serialization(self):
        pickle.dumps(self.rwlock)
        self.assertTrue(True)

    def test_deserialization(self):
        s = pickle.dumps(self.rwlock)
        t = pickle.loads(s)
        self.assertEquals(t._fd, self.rwlock._fd)

    def test_cleanup(self):
        os.close(self.rwlock._fd)
        del self.rwlock
        self.assertTrue(True)

    def test_read_release(self):
        self.rwlock.acquire_read()
        self.rwlock.release()

    def test_write_release(self):
        self.rwlock.acquire_write()
        self.rwlock.release()

    # def test_exhaust_memory(self):
    #     try:
    #         self.allocate_infinitely()
    #         self.assertTrue(False)
    #     except mmap.error:
    #         self.assertTrue(True)
    #     except OSError:
    #         # We might hit a limit of open files before exhausting memory
    #         self.assertTrue(True)

    def test_child_interaction(self):
        children = 10
        pool = Pool(processes=children)
        ret = [pool.apply_async(f, args=[self.rwlock])
               for i in range(children)]
        time.sleep(.1)
        self.rwlock.acquire_write()
        time.sleep(2)
        self.rwlock.release()
        pool.close()
        pool.join()
        self.assertTrue(all([r.successful() for r in ret]))

    def test_wrong_constant(self):
        prwlock.set_pthread_process_shared(0xbeef)
        with self.assertRaises(OSError):
            prwlock.RWLock()

    def acquire_lock(self, function, rwlock, queue, expected_result=True):
        p = mp.Process(target=function, args=(rwlock, queue,))
        p.start()
        if expected_result:
            self.assertTrue(queue.get())
        else:
            self.assertFalse(queue.get())
        p.join()

    def test_timeout(self):
        # Lock write first
        self.rwlock.acquire_write()
        q = mp.Queue()
        # Test acquire read timeout
        self.acquire_lock(acquire_read_timeout, self.rwlock, q, False)
        # test acquire write timeout
        self.acquire_lock(acquire_write_timeout, self.rwlock, q, False)
        # Release lock and try again
        self.rwlock.release()
        # Now try to get read lock
        self.acquire_lock(acquire_read_timeout, self.rwlock, q, True)
        # test acquire write timeout
        self.acquire_lock(acquire_write_timeout, self.rwlock, q, True)

    def test_try_acquire(self):
        # Lock write first
        self.rwlock.acquire_write()
        q = mp.Queue()
        self.acquire_lock(try_acquire_write, self.rwlock, q, False)
        self.acquire_lock(try_acquire_read, self.rwlock, q, False)
        # Release lock and try again
        self.rwlock.release()
        self.acquire_lock(try_acquire_write, self.rwlock, q, True)
        self.acquire_lock(try_acquire_read, self.rwlock, q, True)

    def test_context_managers(self):
        accessed_protected_area = False
        with self.rwlock.reader_lock(timeout=1):
            pass
        with self.rwlock.writer_lock(timeout=1):
            pass
        with self.assertRaises(ValueError):
            with self.rwlock.reader_lock(timeout=.1):
                with self.rwlock.writer_lock(timeout=.1):
                    accessed_protected_area = True
        self.assertFalse(accessed_protected_area)


def f(rwlock):
    for i in range(2):
        rwlock.acquire_read()
        time.sleep(1)
        rwlock.release()
        time.sleep(.1)


def acquire_read_timeout(rwlock, queue):
    ret = rwlock.acquire_read(.3)
    queue.put(ret)
    if ret:
        rwlock.release()


def acquire_write_timeout(rwlock, queue):
    ret = rwlock.acquire_write(.3)
    queue.put(ret)
    if ret:
        rwlock.release()


def try_acquire_write(rwlock, queue):
    ret = rwlock.try_acquire_write()
    queue.put(ret)
    if ret:
        rwlock.release()


def try_acquire_read(rwlock, queue):
    ret = rwlock.try_acquire_read()
    queue.put(ret)
    if ret:
        rwlock.release()
