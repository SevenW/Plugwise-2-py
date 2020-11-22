import os
import sys

from setuptools import setup, find_packages

VERSION = '2.0'

install_reqs = ['crcmod', 'paho-mqtt', 'pyserial']

setup(name='plugwise2py', 
    version=VERSION,
    description='A server to control and log readings form Plugwise devices.',
    author='Seven Watt',
    author_email='info@sevenwatt.com',
    url='https://github.com/SevenW/Plugwise-2-py',
    license='GPL',
    packages=find_packages(),
    py_modules=['plugwise'],
    install_requires=install_reqs,
    scripts=['Plugwise-2.py', 'Plugwise-2-web.py', 'swutil/util.py'],
)

