from __future__ import print_function

import time
import pickle
import unittest

import prwlock
from multiprocessing import Pool

class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.rwlock = prwlock.RWLock()


class RWLockTestCase(BaseTestCase):

    def test_double_release(self):
        with self.assertRaises(ValueError):
            self.rwlock.release_read()

    def test_serialization(self):
        pickle.dumps(self.rwlock)
        self.assertTrue(True)

    def test_deserialization(self):
        s = pickle.dumps(self.rwlock)
        t = pickle.loads(s)
        self.assertEquals(t._mtag, self.rwlock._mtag)

    def test_read_release(self):
        self.rwlock.acquire_read()
        self.rwlock.release_read()
        self.assertTrue(True)

    def test_write_release(self):
        self.rwlock.acquire_write()
        self.rwlock.release_write()
        self.assertTrue(True)

    def test_child_interaction(self):
        children = 3
        pool = Pool(processes=children)
        ret = [pool.apply_async(f, args=[self.rwlock]) for i in range(children)]
        time.sleep(.1)
        self.rwlock.acquire_write()
        time.sleep(4)
        self.rwlock.release_write()
        pool.close()
        pool.join()
        self.assertTrue(all([r.successful() for r in ret]))


def f(rwlock):
    rwlock.acquire_read()
    time.sleep(1)
    rwlock.release_read()
    time.sleep(.1)
