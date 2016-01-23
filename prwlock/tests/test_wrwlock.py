from __future__ import print_function

import time
import pickle
import unittest

import prwlock
from multiprocessing import Pool
import multiprocessing as mp


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.rwlock = prwlock.RWLock()


class RWLockTestCase(BaseTestCase):

    def test_double_release(self):
        with self.assertRaises(ValueError):
            self.rwlock.release()

    def test_serialization(self):
        pickle.dumps(self.rwlock)
        self.assertTrue(True)

    def test_deserialization(self):
        s = pickle.dumps(self.rwlock)
        t = pickle.loads(s)
        self.assertEquals(t._mtag, self.rwlock._mtag)

    def test_read_release(self):
        self.rwlock.acquire_read()
        self.rwlock.release()
        self.assertTrue(True)

    def test_write_release(self):
        self.rwlock.acquire_write()
        self.rwlock.release()
        self.assertTrue(True)

    def test_timeout(self):
        # Lock write first
        self.rwlock.acquire_write()
        q = mp.Queue()
        # Test acquire read timeout
        p = mp.Process(target=acquire_read_timeout, args=(self.rwlock, q,))
        p.start()
        self.assertFalse(q.get())
        p.join()
        # test acquire write timeout
        p = mp.Process(target=acquire_write_timeout, args=(self.rwlock, q,))
        p.start()
        self.assertFalse(q.get())
        p.join()

        # Release lock and try again
        self.rwlock.release()
        # Now try to get read lock
        p = mp.Process(target=acquire_read_timeout, args=(self.rwlock, q,))
        p.start()
        self.assertTrue(q.get())
        p.join()
        # test acquire write timeout
        p = mp.Process(target=acquire_write_timeout, args=(self.rwlock, q,))
        p.start()
        self.assertTrue(q.get())
        p.join()


    def test_child_interaction(self):
        children = 3
        pool = Pool(processes=children)
        ret = [pool.apply_async(f, args=[self.rwlock])
               for i in range(children)]
        time.sleep(.1)
        self.rwlock.acquire_write()
        time.sleep(4)
        self.rwlock.release()
        pool.close()
        pool.join()
        self.assertTrue(all([r.successful() for r in ret]))

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

def f(rwlock):
    rwlock.acquire_read()
    time.sleep(1)
    rwlock.release()
    time.sleep(.1)
