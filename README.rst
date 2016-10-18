Process-shared Reader-Writer locks for Python
=============================================

.. image:: https://travis-ci.org/trovao/prwlock.svg
    :target: https://travis-ci.org/trovao/prwlock

.. image:: https://coveralls.io/repos/trovao/prwlock/badge.svg?branch=master&service=github
    :target: https://coveralls.io/github/trovao/prwlock?branch=master

A `reader-writer lock <https://en.wikipedia.org/wiki/Readers%E2%80%93writer_lock>`_ for
Python that can (*must*, actually) be used for locking across multiple Python processes.

The rationale and initial implementation of the project can be found in the
`accompanying blog post <https://renatocunha.com/blog/2015/11/ctypes-mmap-rwlock/>`_.

Installation
------------

This package is `available on PyPi
<https://pypi.python.org/pypi/prwlock>`_, so you can install the latest stable
release with a simple `pip` call:

.. code-block:: bash

    $ pip install prwlock

Usage
-----

All you have to do is import the module and start using it. There is no need
for initialization. Therefore, a code block such as the one below is enough to
get an RWLock instance.

.. code-block:: python

    from prwlock import RWLock

    rwlock = RWLock()

The RWLock itself is pickleable and, therefore, can be passed around to child processes,
such as in the code block below.

.. code-block:: python

    from __future__ import print_function

    import os
    import time

    from multiprocessing import Pool
    from prwlock import RWLock
    def f(rwlock):
        for i in range(2):
            print(os.getpid(), 'Acquiring read lock')
            rwlock.acquire_read()
            print(os.getpid(), 'Sleeping for a while')
            time.sleep(1)
            print(os.getpid(), 'Releasing lock')
            rwlock.release()
            time.sleep(.1)

    r = RWLock()
    children = 20
    pool = Pool(processes=children)
    for child in range(children):
        pool.apply_async(f, [r])

Context Managers
^^^^^^^^^^^^^^^^^

`prwlock` also supports context managers using the `with` syntax. The code
block below displays one possible way of using it.

.. code-block:: python

    from prwlock import RWLock

    # First you instantiate the lock
    rwlock = RWLock()

    # Now you can lock it in read or in write mode
    with rwlock.reader_lock():
        # If this executes, then reader lock access has been acquired
        print('Reading data')

    # Likewise, you can lock in writer mode with:
    with rwlock.writer_lock():
        print('Writing data')

Contributors
------------

 * `Renato Cunha <https://renatocunha.com>`_
 * `Marcos Assunção <https://marcosassuncao.com>`_
 * `Vyronas Tsingaras <https://vtsingaras.me/>`_

Changes
-------

* 0.4.0: Added context-management support using the `with` syntax;
* 0.3.0: Completed the API's implementation. Namely:
     * Added support for immediate failure when locks cannot be obtained;
     * Added timeouts for obtaining the locks.
* 0.2.0: Added support for RWLocks on Windows XP and above. Changed the API so
  that the lock can be imported as `from prwlock import RWLock`, instead of the
  slightly awkward `from prwlock.prwlock import RWLock` method.
* 0.1.1: Fixed the value of the `PTHREAD_PROCESS_SHARED` constant for Mac OS
  X. Also added a check to prevent double destruction of the underlying lock
  on Mac OS X.
* 0.1.0: Initial release
