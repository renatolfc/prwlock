import os
import time

from prwlock import RWLock
from multiprocessing import Pool

rwlock = RWLock()

def f():
    for i in range(2):
        print(os.getpid(), 'Acquiring read lock')
        rwlock.acquire_read()
        print(os.getpid(), 'Sleeping for a while')
        time.sleep(1)
        print(os.getpid(), 'Releasing lock')
        rwlock.release()
        time.sleep(.1)

if __name__ == '__main__':
    pool = Pool(processes=2)
    pool.apply_async(f)
    pool.apply_async(f)
    time.sleep(.1)
    print('parent Acquiring write lock')
    rwlock.acquire_write()
    print('parent Sleeping for a while')
    time.sleep(2)
    print('parent Releasing lock')
    rwlock.release()
    pool.close()
    pool.join()
    
