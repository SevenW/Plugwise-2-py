# Copyright (C) 2012,2013,2014 Seven Watt <info@sevenwatt.com>
# <http://www.sevenwatt.com>
#
# This file is part of Plugwise-2-py.
#
# Plugwise-2-py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Plugwise-2-py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Plugwise-2-py.  If not, see <http://www.gnu.org/licenses/>. 
#
# The program is a major modification and extension to:
#   python-plugwise - written in 2011 by Sven Petai <hadara@bsd.ee> 
# which itself has integrated parts of Plugwise-on-Linux (POL):
#   POL v0.2 - written in 2009 by Maarten Damen <http://www.maartendamen.com>

import sys
import serial

DEBUG_PROTOCOL = False

def _string_convert_py3(s):
    if type(s) == type(b''):
        return s

    return bytes(s, 'latin-1')

def _string_convert_py2(s):
    # NOOP
    return s

if sys.version_info < (3, 0):
    sc = _string_convert_py2
else:
    sc = _string_convert_py3

def hexstr(s):
    return ' '.join(hex(ord(x)) for x in s)

def debug(msg):
    if __debug__ and DEBUG_PROTOCOL:
        print(msg)

def error(msg):
    # XXX: we currently have far to many false "protocol errors"  since we don't look for ACKs etc.
    # so just ignore these for now unless the debug is set
    return debug(msg)

class SerialComChannel(object):
    """simple wrapper around serial module"""

    def __init__(self, port="/dev/ttyUSB0", baud=115200, bits=8, stop=1, parity='N', timeout=5):
        self.port = port
        self.baud = baud
        self.bits = bits
        self.stop = stop
        self.parity = parity
        self._fd = serial.Serial(port, baudrate=baud, bytesize=bits, stopbits=stop, parity=parity, timeout=timeout)

    def open(self):
        self._fd = Serial(port=self.port, baudrate=self.baud, bytesize=self.bits, parity='N', stopbits=stop)

    def read(self, bytecount):
        return self._fd.read(bytecount)

    def readline(self):
        return self._fd.readline()

    def write(self, data):
        self._fd.write(data)
