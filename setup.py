import os
import sys

from setuptools import setup, find_packages

VERSION = '2.0'

install_reqs = ['crcmod']

if sys.version_info < (3, 0):
    install_reqs.append('pyserial')
else:
    install_reqs.append('pyserial-py3k')

setup(name='Plugwise-2-py', 
    version=VERSION,
    description='A library for controlling and data logging with Plugwise smartplugs',
    author='Seven Watt',
    author_email='info@sevenwatt.com',
    url='https://github.com/SevenW/Plugwise-2-py',
    license='GPLv3',
    packages=find_packages(),
    py_modules=['plugwise'],
    install_requires=install_reqs,
    scripts=['plugwise_util'],
)
