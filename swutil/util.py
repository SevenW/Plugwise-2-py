# Copyright (C) 2012,2013,2014,2015 Seven Watt <info@sevenwatt.com>
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
# which itself is inspired by Plugwise-on-Linux (POL):
#   POL v0.2 - written in 2009 by Maarten Damen <http://www.maartendamen.com>

import sys
import serial
import datetime
import logging
import logging.handlers

LOG_COMMUNICATION = False

#global var
pw_logger = None
pw_comm_logger = None

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
    
def uint_to_int(val, octals):
    """compute the 2's compliment of int value val for negative values"""
    bits=octals<<2
    if( (val&(1<<(bits-1))) != 0 ):
        val = val - (1<<bits)
    return val
    
def int_to_uint(val, octals):
    """compute the 2's compliment of int value val for negative values"""
    bits=octals<<2
    if val<0:
        val = val + (1<<bits)
    return val

def init_logger(logfname, appname='plugwise2py'):
    global pw_logger
    pw_logger = logging.getLogger(appname)
    log_level()
    # Add the log message handler to the logger
    handler = logging.handlers.RotatingFileHandler(logfname, maxBytes=1000000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    pw_logger.addHandler(handler)
    pw_logger.info("logging started")
   
def log_level(level=logging.DEBUG):
    pw_logger.setLevel(level)

def log_comm(enable):
    global LOG_COMMUNICATION
    LOG_COMMUNICATION = enable

def debug(msg):
    #if __debug__ and DEBUG_PROTOCOL:
        #print("%s: %s" % (datetime.datetime.now().isoformat(), msg,))
        #print(msg)
    pw_logger.debug(msg)

def error(msg, level=1):
    #if level <= LOG_LEVEL:
        #print("%s: %s" % (datetime.datetime.now().isoformat(), msg,))
    pw_logger.error(msg)
        
def info(msg):
    #print("%s: %s" % (datetime.datetime.now().isoformat(), msg,))
    pw_logger.info(msg)

def open_logcomm(filename):
    global pw_comm_logger
    pw_comm_logger = logging.getLogger("pwcomm")
    # Add the log message handler to the logger
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1000000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)
    pw_comm_logger.addHandler(handler)
    pw_comm_logger.setLevel(logging.INFO) 
    pw_comm_logger.info("logging started")
    #global logcommfile
    #logcommfile = open(filename, 'w')
    
def close_logcomm():
    #logcommfile.close()
    return
    
def logcomm(msg):
    info("COMMU called logcomm type %s value %s" % (type(LOG_COMMUNICATION), LOG_COMMUNICATION))
    if LOG_COMMUNICATION:
        #logcommfile.write("%s %s \n" % (datetime.datetime.now().isoformat(), msg,))
        pw_comm_logger.info(msg)

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
