# Copyright (C) 2012,2013,2014,2015,2016,2017,2018,2019,2020 Seven Watt <info@sevenwatt.com>
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

import struct
import binascii
import datetime
from .exceptions import *

from swutil.util import *

DEBUG_PROTOCOL = False

# plugwise year information is offset from y2k
PLUGWISE_EPOCH = 2000

import crcmod

crc_fun = crcmod.mkCrcFun(0x11021, rev=False, initCrc=0x0000, xorOut=0x0000)

class UnexpectedResponse(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class OutOfSequenceException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class BaseType(object):
    def __init__(self, value, length):
        self.value = value
        self.length = length

    def serialize(self):
        return self.value

    def unserialize(self, val):
        self.value = val

    def __len__(self):
        return self.length

class CompositeType(BaseType):
    def __init__(self):
        self.contents = []

    def serialize(self):
        return b''.join(a.serialize() for a in self.contents)

    def unserialize(self, val):
        for p in self.contents:
            myval = val[:len(p)]
            #debug("PARS      "+repr(str(myval)))
            p.unserialize(myval)
            debug("PARS      "+ logf(myval) + " EVAL "+str(p.value))
            val = val[len(myval):]
        return val
        
    def __len__(self):
        return sum(len(x) for x in self.contents)

class String(BaseType):
    def serialize(self):
        return self.value.encode()
    
class StringVal(BaseType):
    def __init__(self, value, length=2):
        self.value = value
        self.length = length
                
    def serialize(self):
        fmt = b"%%0%dd" % self.length
        return fmt % self.value

    def unserialize(self, val):
        try:
            self.value = int(val)
        except ValueError:
            debug('value error while attempting to construct StringVal object. val = %s' % val)
            self.value = 0

class SInt(BaseType):
    def __init__(self, value, length=2):
        self.value = value
        self.length = length
                
    def negative(self, val, octals):
        """compute the 2's compliment of int value val for negative values"""
        bits=octals<<2
        if( (val&(1<<(bits-1))) != 0 ):
            val = val - (1<<bits)
        return val

    def serialize(self):
        fmt = b"%%0%dX" % self.length
        return fmt % int_to_uint(self.value, self.length)

    def unserialize(self, val):
        self.value = self.negative(int(val,16), self.length)
    
class Int(BaseType):
    def __init__(self, value, length=2):
        self.value = value
        self.length = length

    def serialize(self):
        fmt = b"%%0%dX" % self.length
        return fmt % self.value

    def unserialize(self, val):
        self.value = int(val, 16)

class UnixTimestamp(Int):
    def __init__(self, value, length=8):
        Int.__init__(self, value, length=length)

    def unserialize(self, val):
        Int.unserialize(self, val)
        self.value = datetime.datetime.fromtimestamp(self.value)

class Year2k(Int):
    """year value that is offset from the year 2000"""

    def unserialize(self, val):
        Int.unserialize(self, val)
        self.value += PLUGWISE_EPOCH

class DateTime(CompositeType):
    """datetime value as used in the general info response
    format is: YYMMmmmm
    where year is offset value from the epoch which is Y2K
    and last four bytes are offset from the beginning of the month in minutes
    """

    def __init__(self, year=0, month=0, minutes=0):
        CompositeType.__init__(self)        
        self.year = Year2k(year-PLUGWISE_EPOCH, 2)
        self.month = Int(month, 2)
        self.minutes = Int(minutes, 4)
        self.contents += [self.year, self.month, self.minutes]

    def unserialize(self, val):
        CompositeType.unserialize(self, val)
        minutes = self.minutes.value
        hours = minutes // 60
        days = hours // 24
        hours -= (days*24)
        minutes -= (days*24*60)+(hours*60)
        try:
            self.value = datetime.datetime(self.year.value, self.month.value, days+1, hours, minutes)
        except ValueError:
            debug('value error while attempting to construct datetime object')
            self.value = None

class Time(CompositeType):
    """time value as used in the clock info response"""

    def __init__(self, hour=0, minute=0, second=0):
        CompositeType.__init__(self)
        self.hour = Int(hour, 2)
        self.minute = Int(minute, 2)
        self.second = Int(second, 2)
        self.contents += [self.hour, self.minute, self.second]

    def unserialize(self, val):
        CompositeType.unserialize(self, val)
        self.value = datetime.time(self.hour.value, self.minute.value, self.second.value)
        
class DateStr(CompositeType):
    """date value as used in the datetime info response"""

    def __init__(self, day=0, month=0, year=0):
        CompositeType.__init__(self)
        self.day = StringVal(day, 2)
        self.month = StringVal(month, 2)
        self.year = StringVal(year, 2)
        self.contents += [self.day, self.month, self.year]

    def unserialize(self, val):
        CompositeType.unserialize(self, val)
        try:
            self.value = datetime.date(self.year.value+PLUGWISE_EPOCH, self.month.value, self.day.value)
        except ValueError:
            debug('value error while attempting to construct DateStr object')
            self.value = None
       
class TimeStr(CompositeType):
    """time value as used in the datetime info response"""

    def __init__(self, second=0, minute=0, hour=0):
        CompositeType.__init__(self)
        self.second = StringVal(second, 2)
        self.minute = StringVal(minute, 2)
        self.hour = StringVal(hour, 2)
        self.contents += [self.second, self.minute, self.hour]

    def unserialize(self, val):
        CompositeType.unserialize(self, val)
        self.value = datetime.time(self.hour.value, self.minute.value, self.second.value)
       
class Float(BaseType):
    def __init__(self, value, length=4):
        self.value = value
        self.length = length

    def unserialize(self, val):
        hexval = binascii.unhexlify(val)
        self.value = struct.unpack("!f", hexval)[0]

class LogAddr(Int):
    LOGADDR_OFFSET = 278528

    def serialize(self):
        return b"%08X" % ((self.value * 32) + self.LOGADDR_OFFSET)

    def unserialize(self, val):
        Int.unserialize(self, val)
        self.value = (self.value - self.LOGADDR_OFFSET) // 32

# /base types

class PlugwiseMessage(object):
    PACKET_HEADER = b'\x05\x05\x03\x03'
    PACKET_HEADER5 = b'\x83\x05\x05\x03\x03'
    PACKET_FOOTER = b'\x0d\x0a'
    
    def serialize(self):
        """return message in a serialized format that can be sent out
        on wire
        """
        args = b''.join(a.serialize() for a in self.args)
        msg = self.ID+self.mac+args
        checksum = self.calculate_checksum(msg)
        full_msg = self.PACKET_HEADER+msg+checksum+self.PACKET_FOOTER
        logcomm("SEND %4d ---> %4s           %16s %s %4s <---" % (len(full_msg), self.ID.decode(), self.mac.decode(), args.decode(), checksum.decode()))        
        return full_msg

    def calculate_checksum(self, s):
        return b"%04X" % crc_fun(s)

class PlugwiseResponse(PlugwiseMessage):
    ID = b'FFFF'
    
    def __init__(self, seqnr = None):
        PlugwiseMessage.__init__(self)
        self.params = []

        self.mac = None
        self.function_code = None
        self.command_counter = None
        self.expected_command_counter = seqnr

    def unserialize(self, response):
        # FIXME: avoid magic numbers

        header5 = False
        header_start = response.find(PlugwiseMessage.PACKET_HEADER5)
        if header_start == 0:
            #A response from a circle seems to be preceeded by the x/83 in the header
            #Just strip this character to not further complcate the code
            response = response[1:]
            header5 = True
                
        header, self.function_code, self.command_counter = struct.unpack("4s4s4s", response[:12])
        crc, footer = struct.unpack("4s2s", response[-6:])
        raw_msg_len = len(response)
        

        #check for protocol errors
        protocol_error = ''
        if footer != self.PACKET_FOOTER:
            protocol_error = "broken footer!"
        else:
            footer = '<---'
        if header != self.PACKET_HEADER:
            protocol_error = "broken header!"
        else:
            if header5:
                header = '-->>'
            else:
                header = '--->'
        if crc != self.calculate_checksum(response[4:-6]):
            protocol_error = "checksum error!"
        debug("STRU      "+header+" "+logf(self.function_code)+" "+logf(self.command_counter)+" <data> "+logf(crc)+" "+footer)
        if len(protocol_error) > 0:
            raise ProtocolError(protocol_error)
            
        if self.function_code in [b'0000', b'0002', b'0003', b'0005']:
            response = response[12:-6]
        else:
            self.mac = response[12:28]
            response = response[28:-6]
        debug("DATA %4d %s" % (len(response), logf(response)))
        
        if self.function_code in [b'0006', b'0061']:
            error("response.unserialize: detected %s expected %s" % (logf(self.function_code), logf(self.ID)))
        
        if self.expected_command_counter != None and self.expected_command_counter != self.command_counter:
            raise OutOfSequenceException("expected seqnr %s, received seqnr %s - this may be a duplicate message" % (logf(self.expected_command_counter), logf(self.command_counter)))
        if self.ID != 'FFFF' and self.function_code != self.ID:
            raise UnexpectedResponse("expected response code %s, received code %s" % (logf(self.ID), logf(self.function_code)))
        if raw_msg_len != len(self):
            raise UnexpectedResponse("response doesn't have expected length. expected %d bytes got %d" % (len(self), raw_msg_len))
        
        #log communication when no exceptions will be raised
        if self.mac is None:
            logmac = b'................'
        else:
            logmac = self.mac
        if self.function_code in [b'0000', b'0003', b'0005']:
            #HACK: retrieve info from Acq and AcqMac responses
            respstatus = response[:4]
            logresp = b''
            if raw_msg_len == 38:
                logmac = response[4:]
        else:
            respstatus = b'....'
            logresp = response
        logcomm("RECV %4d %s %4s %4s %4s %16s %s %4s %s" % 
            (raw_msg_len, header, self.function_code.decode(), self.command_counter.decode(),
            respstatus.decode(), logmac.decode(),
            logresp.decode(), crc.decode(), footer))
        
        # FIXME: check function code match
        response = self._parse_params(response)

    def _parse_params(self, response):
        for p in self.params:
            myval = response[:len(p)]
            debug("PARS      "+logf(myval))
            p.unserialize(myval)
            debug("PARS      "+logf(myval) + " EVAL "+str(p.value))
            response = response[len(myval):]
        return response

    def __len__(self):
        arglen = sum(len(x) for x in self.params)
        return 34 + arglen

class PlugwiseAckResponse(PlugwiseResponse):
    ID = b'0000'
    
    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.status = Int(0, 4)
        self.params += [self.status]

        self.mac = None
        self.command_counter = None
        
    def __len__(self):
        arglen = sum(len(x) for x in self.params)
        return 18 + arglen

    def unserialize(self, response):
        try:
            PlugwiseResponse.unserialize(self, response)
        except UnexpectedResponse as reason:
            if self.function_code != None and self.function_code in ['0006', '0061']:
                debug("PlugwiseAckResponse.unserialize()  Unjoined node. Do we ever arrive here?")
                raise
            elif self.expected_command_counter is None:
                #In case of awaiting an Ack without knowing a seqnr, the most likely reason of
                #an UnexpectedResponse is a duplicate (ghost) response from an older SEND request.
                raise OutOfSequenceException("expected command ack from stick. received message with seqnr %s - this may be a duplicate message" % (logf(self.command_counter),))
            else:
                raise
 

class PlugwiseAckMacResponse(PlugwiseAckResponse):
    ID = b'0000'

    def __init__(self, seqnr = None):
        PlugwiseAckResponse.__init__(self, seqnr)
        self.acqmac = String(None, length=16)
        self.params += [self.acqmac]
        
    def unserialize(self, response):
        PlugwiseAckResponse.unserialize(self, response)
        self.mac = self.acqmac.value

class PlugwiseCalibrationResponse(PlugwiseResponse):
    ID = b'0027'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.gain_a = Float(0, 8)
        self.gain_b = Float(0, 8)
        self.off_tot = Float(0, 8)
        self.off_noise = Float(0, 8)
        self.params += [self.gain_a, self.gain_b, self.off_tot, self.off_noise]

class PlugwiseClockInfoResponse(PlugwiseResponse):
    ID = b'003F'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.time = Time()
        self.day_of_week = Int(0, 2)
        self.unknown = Int(0, 2)
        self.scheduleCRC = Int(0, 4)
        self.params += [self.time, self.day_of_week, self.unknown, self.scheduleCRC]

class PlugwisePowerUsageResponse(PlugwiseResponse):
    """returns power usage as impulse counters for several different timeframes
    """
    ID = b'0013'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.pulse_1s = SInt(0, 4)
        self.pulse_8s = SInt(0, 4)
        self.pulse_hour = Int(0, 8)
        self.pulse_prod_hour = SInt(0, 8)
        self.unknown2 = Int(0, 4)
        self.params += [self.pulse_1s, self.pulse_8s, self.pulse_hour, self.pulse_prod_hour, self.unknown2]

class PlugwisePowerBufferResponse(PlugwiseResponse):
    """returns information about historical power usage
    each response contains 4 log buffers and each log buffer contains data for 1 hour
    """
    ID = b'0049'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.logdate1 = DateTime()
        self.pulses1 = SInt(0, 8)
        self.logdate2 = DateTime()
        self.pulses2 = SInt(0, 8)
        self.logdate3 = DateTime()
        self.pulses3 = SInt(0, 8)
        self.logdate4 = DateTime()
        self.pulses4 = SInt(0, 8)
        self.logaddr = LogAddr(0, length=8)
        self.params += [self.logdate1, self.pulses1, self.logdate2, self.pulses2,
            self.logdate3, self.pulses3, self.logdate4, self.pulses4, self.logaddr
        ]

class PlugwisePowerBufferResponseRaw(PlugwiseResponse):
    """returns information about historical power usage
    each response contains 4 log buffers and each log buffer contains data for 1 hour
    """
    ID = b'0049'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.raw = String(None, length=64)
        self.logaddr = LogAddr(0, length=8)
        self.params += [self.raw, self.logaddr
        ]

class PlugwiseInfoResponse(PlugwiseResponse):
    ID = b'0024'
    
    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.datetime = DateTime()
        self.last_logaddr = LogAddr(0, length=8)
        self.relay_state = Int(0, length=2)
        self.hz = Int(0, length=2)
        self.hw_ver = String(None, length=12)
        self.fw_ver = UnixTimestamp(0)
        self.type = Int(0, length=2)
        self.params += [
            self.datetime,
            self.last_logaddr, self.relay_state, 
            self.hz, self.hw_ver, self.fw_ver, self.type
        ]

class PlugwiseStatusResponse(PlugwiseResponse):
    ID = b'0011'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.is_new_protocol_version = Int(0, length=2)
        self.network_is_online = Int(0, length=2)
        self.network_id = Int(0, length=16)
        self.network_id_short = Int(0, length=4)
        self.unused = Int(0, length=2)
        self.params += [
            self.is_new_protocol_version,
            self.network_is_online,
            self.network_id,
            self.network_id_short,
            self.unused,
        ]

class PlugwiseFeatureSetResponse(PlugwiseResponse):
    """returns feature set of modules
    """
    ID = b'0060'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.features = Int(0, 16)
        self.params += [self.features]
        
class PlugwiseDateTimeInfoResponse(PlugwiseResponse):
    ID = b'003A'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.time = TimeStr()
        self.day_of_week = Int(0, 2)
        self.date = DateStr()
        self.params += [self.time, self.day_of_week, self.date]

class PlugwiseSendScheduleResponse(PlugwiseResponse):
    ID = b'003D'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.idx = Int(0, 2)
        self.params += [self.idx]
              
class PlugwisePingResponse(PlugwiseResponse):
    ID = b'000E'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.qin = Int(0, 2)
        self.qout = Int(0, 2)
        self.pingtime = Int(0, 4)
        self.params += [self.qin, self.qout, self.pingtime]
              
class PlugwiseAssociatedNodesResponse(PlugwiseResponse):
    ID = b'0019'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.node_mac_id = String(None, length=16)
        self.idx = Int(0, 2)
        self.params += [self.node_mac_id, self.idx]
              
class PlugwiseAdvertiseNodeResponse(PlugwiseResponse):
    ID = b'0006'
    #this messages uses its own sequence counter so are received as "OutOfSequenceException"

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
              
class PlugwiseQueryCirclePlusResponse(PlugwiseResponse):
    ID = b'0002'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.channel = String(None, length=2)
        self.source_mac_id = String(None, length=16)
        self.extended_pan_id = String(None, length=16)
        self.unique_network_id = String(None, length=16)
        self.new_node_mac_id = String(None, length=16)
        self.pan_id = String(None, length=4)
        self.idx = Int(0, length=2)
        self.params += [self.channel, self.source_mac_id, self.extended_pan_id, self.unique_network_id, self.new_node_mac_id, self.pan_id, self.idx]
        
    def __len__(self):
        arglen = sum(len(x) for x in self.params)
        return 18 + arglen

    def unserialize(self, response):
        PlugwiseResponse.unserialize(self, response)
        #Clear first two characters of mac ID, as they contain part of the short PAN-ID
        self.new_node_mac_id.value = b'00'+self.new_node_mac_id.value[2:]
        
class PlugwiseQueryCirclePlusEndResponse(PlugwiseResponse):
    ID = b'0003'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.status = Int(0, 4)
        self.params += [self.status]
       
    def __len__(self):
        arglen = sum(len(x) for x in self.params)
        return 18 + arglen
        
class PlugwiseConnectCirclePlusResponse(PlugwiseResponse):
    ID = b'0005'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.exsisting = Int(0, 2)
        self.allowed = Int(0, 2)
        self.params += [self.exsisting, self.allowed]
       
    def __len__(self):
        arglen = sum(len(x) for x in self.params)
        return 18 + arglen

class PlugwiseRemoveNodeResponse(PlugwiseResponse):
    ID = b'001D'

    def __init__(self, seqnr = None):
        PlugwiseResponse.__init__(self, seqnr)
        self.node_mac_id = String(None, length=16)
        self.status = Int(0, 2)
        self.params += [self.node_mac_id, self.status]  

class PlugwiseAckAssociationResponse(PlugwiseResponse):
    ID = b'0061'

    def __init__(self, seqnr = None):
        #sequence number is always FFFD
        PlugwiseResponse.__init__(self, 0xFFFD)       
        
class PlugwiseRequest(PlugwiseMessage):
    def __init__(self, mac):
        PlugwiseMessage.__init__(self)
        self.args = []
        self.mac = mac

class PlugwiseStatusRequest(PlugwiseRequest):
    """Get Stick Status"""
    ID = b'000A'

    def __init__(self):
        """message for that initializes the Stick"""
        # status doesn't send MAC address
        PlugwiseRequest.__init__(self, b'')

class PlugwisePowerUsageRequest(PlugwiseRequest):
    ID = b'0012'

class PlugwiseInfoRequest(PlugwiseRequest):
    ID = b'0023'

class PlugwiseClockInfoRequest(PlugwiseRequest):
    ID = b'003E'

class PlugwiseClockSetRequest(PlugwiseRequest):
    ID = b'0016'

    def __init__(self, mac, dt):
        PlugwiseRequest.__init__(self, mac)
        passed_days = dt.day - 1
        month_minutes = (passed_days*24*60)+(dt.hour*60)+dt.minute
        d = DateTime(dt.year, dt.month, month_minutes)
        t = Time(dt.hour, dt.minute, dt.second)
        day_of_week = Int(dt.weekday() + 1, 2)
        # FIXME: use LogAddr instead
        log_buf_addr = String('FFFFFFFF', 8)
        self.args += [d, log_buf_addr, t, day_of_week]

class PlugwiseSwitchRequest(PlugwiseRequest):
    """switches Plug on or off"""
    ID = b'0017'
    
    def __init__(self, mac, on):
        PlugwiseRequest.__init__(self, mac)
        val = 1 if on == True else 0
        self.args.append(Int(val, length=2))

class PlugwiseCalibrationRequest(PlugwiseRequest):
    ID = b'0026'

class PlugwisePowerBufferRequest(PlugwiseRequest):
    ID = b'0048'

    def __init__(self, mac, log_address):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(LogAddr(log_address, 8))
        
class PlugwiseLogIntervalRequest(PlugwiseRequest):
    ID = b'0057'

    def __init__(self, mac, usage, production):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(Int(usage, length=4))
        self.args.append(Int(production, length=4))
        
class PlugwiseClearGroupMacRequest(PlugwiseRequest):
    ID = b'0058'

    def __init__(self, mac, taskId):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(Int(taskId, length=2))

class PlugwiseFeatureSetRequest(PlugwiseRequest):
    ID = b'005F'
        
class PlugwiseDateTimeInfoRequest(PlugwiseRequest):
    ID = b'0029'

class PlugwiseSetDateTimeRequest(PlugwiseRequest):
    ID = b'0028'

    def __init__(self, mac, dt):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(StringVal(dt.second, 2))
        self.args.append(StringVal(dt.minute, 2))
        self.args.append(StringVal(dt.hour, 2))
        self.args.append(StringVal(dt.weekday() + 1, 2))
        self.args.append(StringVal(dt.day, 2))
        self.args.append(StringVal(dt.month, 2))
        self.args.append(StringVal((dt.year-PLUGWISE_EPOCH), 2))
    
class PlugwiseEnableScheduleRequest(PlugwiseRequest):
    """switches Schedule on or off"""
    ID = b'0040'
    
    def __init__(self, mac, on):
        PlugwiseRequest.__init__(self, mac)
        val = 1 if on == True else 0
        self.args.append(Int(val, length=2))
        #the second parameter is always 0x01
        self.args.append(Int(1, length=2))

class PlugwisePrepareScheduleRequest(PlugwiseRequest):
    """Send chunck of On/Off/StandbyKiller Schedule to Stick"""
    ID = b'003B'
    
    def __init__(self, idx, schedule_chunk):
        # PrepareScedule doesn't send MAC address
        PlugwiseRequest.__init__(self, '')
        self.args.append(Int(16*idx, length=4))
        for i in range(0,8):
            self.args.append(SInt(schedule_chunk[i], length=4))

class PlugwiseSendScheduleRequest(PlugwiseRequest):
    """Send chunk of  On/Off/StandbyKiller Schedule to Circle(+)"""
    ID = b'003C'
    
    def __init__(self, mac, idx):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(Int(idx, length=2))

class PlugwiseSetScheduleValueRequest(PlugwiseRequest):
    """Send chunk of  On/Off/StandbyKiller Schedule to Circle(+)"""
    ID = b'0059'
    
    def __init__(self, mac, val):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(SInt(val, length=4))

class PlugwisePingRequest(PlugwiseRequest):
    """Send ping to mac"""
    ID = b'000D'
    
    def __init__(self, mac):
        PlugwiseRequest.__init__(self, mac)

class PlugwiseAssociatedNodesRequest(PlugwiseRequest):
    """Send populate request"""
    ID = b'0018'
    
    def __init__(self, mac, idx):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(Int(idx, length=2))

class PlugwiseEnableJoiningRequest(PlugwiseRequest):
    """Send a flag which enables or disables joining nodes (cirles) request"""
    ID = b'0008'
    
    def __init__(self, mac, on):
        PlugwiseRequest.__init__(self, mac)
        #TODO: Make sure that '01' means enable, and '00' disable joining
        val = 1 if on == True else 0
        self.args.append(Int(val, length=2))

class PlugwiseJoinNodeRequest(PlugwiseRequest):
    """Send Join nodes request to add a new node to the network"""
    ID = b'0007'
    
    def __init__(self, mac, permission):
        PlugwiseRequest.__init__(self, mac)
        val = 1 if permission == True else 0
        self.args.append(Int(val, length=2))
        
    #This message has an exceptional format and therefore need to override the serialize method
    def serialize(self):
        """return message in a serialized format that can be sent out
        on wire
        """
        args = b''.join(a.serialize() for a in self.args)
        msg = self.ID+args+self.mac
        checksum = self.calculate_checksum(msg)
        full_msg = self.PACKET_HEADER+msg+checksum+self.PACKET_FOOTER
        logcomm("SEND %4d ---> %4s        %2s %16s %4s <---" % (len(full_msg), self.ID.decode(), args.decode(), self.mac.decode(), checksum.decode()))        
        return full_msg

class PlugwiseQueryCirclePlusRequest(PlugwiseRequest):
    """Query any presence off networks. Maybe intended to find a Circle+ from the Stick"""
    ID = b'0001'

    def __init__(self):
        """message for that initializes the Stick"""
        # init doesn't send MAC address
        PlugwiseRequest.__init__(self, '')

class PlugwiseConnectCirclePlusRequest(PlugwiseRequest):
    """Request connection to the network. Maybe intended to connect a Circle+ to the Stick"""
    ID = b'0004'
    
    def __init__(self, mac):
        PlugwiseRequest.__init__(self, mac)
    
    #This message has an exceptional format and therefore need to override the serialize method
    def serialize(self):
        """return message in a serialized format that can be sent out
        on wire
        """
        #This command has args: byte: key, byte: networkinfo.index, ulong: networkkey = 0
        args = b'00000000000000000000'
        msg = self.ID+args+self.mac
        checksum = self.calculate_checksum(msg)
        full_msg = self.PACKET_HEADER+msg+checksum+self.PACKET_FOOTER
        logcomm("SEND %4d ---> %4s           %s %16s %4s <---" % (len(full_msg), self.ID.decode(), args.decode(), self.mac.decode(), checksum.decode()))        
        return full_msg
    
class PlugwiseRemoveNodeRequest(PlugwiseRequest):
    """Send remove node from network request"""
    ID = b'001C'
    
    def __init__(self, mac, removemac):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(String(removemac, length=16))

class PlugwiseResetRequest(PlugwiseRequest):
    """Send preset circle request"""
    ID = b'0009'
    
    def __init__(self, mac, moduletype, timeout):
        PlugwiseRequest.__init__(self, mac)
        self.args.append(Int(moduletype, length=2))
        self.args.append(Int(timeout, length=2))
        
