"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

import prwlock
import platform

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

if platform.system() == 'Windows':
    test_module = 'prwlock.tests.test_wrwlock'
else:
    test_module = 'prwlock.tests.test_prwlock'

setup(
    name='prwlock',
    version=prwlock.__version__,
    description='Native process-shared rwlock support for Python',
    long_description=long_description,
    url='https://bitbucket.org/prwlock/prwlock',
    author='Renato Cunha, Marcos Assuncao',
    author_email='erangb@erangbphaun.pbz, nffhapnb@npz.bet',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Operating System',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux',
        'Operating System :: POSIX :: BSD :: FreeBSD',
        'Operating System :: POSIX :: BSD :: OpenBSD',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows :: Windows XP',
        'Operating System :: Microsoft :: Windows :: Windows Vista',
        'Operating System :: Microsoft :: Windows :: Windows Server 2003',
        'Operating System :: Microsoft :: Windows :: Windows Server 2008',
        'Operating System :: Microsoft :: Windows :: Windows 7',
    ],
    keywords='rwlock posix process-shared process',
    packages=find_packages(),
    test_suite=test_module,
)
