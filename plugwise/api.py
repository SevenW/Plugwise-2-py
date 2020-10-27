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

# TODO:
#   - make communication channel concurrency safe
#   - return more reasonable responses than response message objects from the functions that don't do so yet
#   - make message construction syntax better. Fields should only be specified once and contain name so we can serialize response message to dict
#   - unit tests
#   - support for older firmware versions

import re
import sys
import time
import math
from datetime import datetime, timedelta
import time
import calendar
import logging
from serial.serialutil import SerialException

from swutil.util import *
from .protocol import *
from .exceptions import *

PULSES_PER_KW_SECOND = 468.9385193

DEFAULT_TIMEOUT = 1

class Stick(SerialComChannel):
    """provides interface to the Plugwise Stick"""

    def __init__(self, port=0, timeout=DEFAULT_TIMEOUT):
        self._devtype = 0 # Stick
        self.pan = None
        self.short_pan = None
        self.mac = None
        self.circleplusmac = None
        self.circles = {} #dictionary {mac, circle} filled by circle init
        self.last_counter = 0
        self.unjoined = set()
        SerialComChannel.__init__(self, port=port, timeout=timeout)
        if self.connected:
            self.init()


    def init(self):
        """send init message to the stick"""
        self.status()

    def reconnect(self):
        """recover from disconnected serial device"""
        try:
            info("Reconnecting to serial device")
            self.close()
            time.sleep(1)
            self.reopen()
        except Exception as e:
            print(e)      
            error("Error: %s" % str(e),) 
        #if init raises an exception, let the application handle it.
        if self.connected:
            self.init()

    def send_msg(self, cmd):
        #log communication done in serialize function of message object. Could be too early!
        debug("SEND %4d %s" % (len(cmd), logf(cmd)))
        try:
            self.write(cmd)
        except SerialException as e:
            print(e)
            info("SerialException during write - recovering. msg %s" % str(e))
            self.reconnect()
        while 1:
            resp = self.expect_response(PlugwiseAckResponse)
            #test on sequence number, to be refined for wrap around
            if (self.last_counter - int(resp.command_counter, 16) >= 0):
                debug("Seqnr already used in send_msg")
            #in case a timeout on previous send occurs, then ignore here.
            if resp.status.value == 0xE1:
                debug("Ignoring 0xE1 status in send_msg")
                continue
            success = False
            if resp.status.value == 0xC1:
                success = True
            self.last_counter = int(resp.command_counter, 16)
            break
        return (success, resp.command_counter)

    def _recv_response(self, retry_timeout=5):
        await_response = True
        msg = b""
        retry_timeout += 1
        while await_response:
            try:
                msg += self.readline()
            except SerialException as e:
                print(e)
                info("SerialException during readline - recovering. msg %s" % str(e))
                self.reconnect()
            # if msg == b"":
                # logcomm("TOUT      '' - <!> Timeout on serial port" )        
                # raise TimeoutException("Timeout while waiting for response from device")                
            # #debug("read:"+logf(msg)+" with length "+str(len(msg)))
            
            # if (msg != b""):
                # if (msg[-1] != '\n'):
                    # logcomm("lastbyte not 0A")
                # else:
                    # logcomm("lastbyte is 0A")
                # try:    
                    # logcomm("last bytes: %04X %04X" % (ord(msg[-2]), ord(msg[-1])))
                # except:
                    # logcomm("last byte : %04X" % (ord(msg[-1]),))
                    # pass
            # logcomm("counter: %2d" % (retry_timeout,))
            if (msg == b"") or ((msg[-1] != ord('\n')) and (msg[-1] != 131)): #131 = 0x83
                retry_timeout -= 1
                if retry_timeout <= 0:
                    if (msg != b""):
                        logcomm("TOUT %4d %s - <!> Timeout on serial port" % ( len(msg), logf(msg)))  
                    else:
                        logcomm("TOUT      '' - <!> Timeout on serial port" )        
                    raise TimeoutException("Timeout while waiting for response from device")
                else:
                    continue
            
            header_start = msg.find(PlugwiseMessage.PACKET_HEADER5)
            if header_start < 0:
                header_start = msg.find(PlugwiseMessage.PACKET_HEADER)
            if header_start > 0:
                ### 2011 firmware seems to sometimes send extra \x83 byte before some of the
                ### response messages but there might a all kinds of chatter going on so just 
                # look for our packet header. Due to protocol errors it might be in the middle of a response
                logcomm("DSTR %4d %s" % ( len(msg[:header_start]), repr(msg[:header_start].decode('utf-8'))))
                msg = msg[header_start:]
                
            if msg.find(b'#') >= 0:
                logcomm("DTRC %4d %s" % ( len(msg), logf(msg)))
                msg = b""
            elif len(msg)<22:
                # Ignore. It is too short to interpet as a message.
                # It may be part of Stick debug messages.
                logcomm("DSHR %4d %s" % ( len(msg), logf(msg)))
                msg = b""
            else:
                #message can be interpreted as response
                #perform logcomm after interpetation of response
                #logcomm("RECV %4d %s" % ( len(msg), logf(msg)))
                await_response = False
        debug("RECV %4d %s" % (len(msg), logf(msg)))
        return msg
        
    def is_in_sequence(self, resp, seqnr):
        if not seqnr is None and resp.command_counter != seqnr:
            error("Out of sequence message. Expected seqnr %s, received seqnr %s" % (seqnr, resp.command_counter))
            return False
        else:
            return True

    def expect_response(self, response_class, src_mac=None, seqnr=None, retry_timeout=5):
        resp = response_class(seqnr)
        # there's a lot of debug info flowing on the bus so it's
        # expected that we constantly get unexpected messages
        while 1:
            try:
                #readlen = len(resp)
                #debug("expecting to read "+str(readlen)+" bytes for msg. "+str(resp))
                msg = self._recv_response(retry_timeout)
                resp.unserialize(msg)
                if self.is_in_sequence(resp, seqnr) and (src_mac is None or src_mac == resp.mac):
                    return resp
                error("expect_response: received response but did not return as expected %s %s %s %s" % (str(seqnr), str(src_mac), str(resp.mac), self.is_in_sequence(resp, seqnr)))
            except ProtocolError as reason:
                #retry to receive the response
                logcomm("RERR %4d %s - <!> protocol error: %s" % ( len(msg), logf(msg), str(reason)))
                error("protocol error [1]:"+str(reason))
            except OutOfSequenceException as reason:
                #retry to receive the response
                #test ping response any offline circle
                try:
                    if resp.function_code == b'000E':
                        info("expect_response: out of sequence PING response")
                        pingresp = PlugwisePingResponse()
                        pingresp.unserialize(msg)
                        circle = self.circles[resp.mac.decode('utf-8')]
                        circle.pong = True
                    elif resp.function_code == b'0006':
                        info("entering unknown advertise MAC [1]")
                        ackresp = PlugwiseAdvertiseNodeResponse()
                        ackresp.unserialize(msg)
                        info("unknown advertise MAC [1] %s" % logf(ackresp.mac))
                        if ackresp.mac.decode('utf-8') not in self.unjoined:
                            self.unjoined.add(ackresp.mac.decode('utf-8'))
                    elif resp.function_code == b'0061':
                        ackresp = PlugwiseAckAssociationResponse()
                        ackresp.unserialize(msg)
                        info("unknown MAC associating [1] %s" % logf(ackresp.mac))
                    else:
                        logcomm("RERR %4d %s - <!> out of sequence: %s" % ( len(msg), logf(msg), str(reason)))
                        error("out of sequence error [2]:"+str(reason))
                #Reinterpretation of response should never raise ProtocolError or UnexpectedResponse
                #OutOfSequenceException is suppressed bu not passing seqnr in Response constructor
                except (OutOfSequenceException, ProtocolError, UnexpectedResponse) as reason:
                    #retry to receive the response
                    logcomm("RERR %4d %s - <!> error while reinterpreting out of sequence response: %s" % ( len(msg), logf(msg), str(reason)))
                    error("error while reinterpreting out of sequence response:"+str(reason))
            except UnexpectedResponse as reason:
                #response could be an error status message
                #suppress error logging when expecting a response to ping in case circle is offline
                #TODO: This logging suppresion is probably no longer required
                if str(reason) != "'expected response code 000E, received code 0000'":
                    error("unexpected response [1]:"+str(reason))
                else:
                    debug("unexpected response [1]:"+str(reason))
                try:
                    if resp.function_code == b'0000' and not issubclass(resp.__class__, PlugwiseAckResponse):
                        #Could be an Ack or AckMac or AcqAssociation error code response when same seqnr
                        if (len(msg) == 22 and msg[0:1] == b'\x05') or (len(msg) == 23 and msg[0:1] == b'\x83'):
                            ackresp = PlugwiseAckResponse()
                            ackresp.unserialize(msg)
                            if self.is_in_sequence(ackresp, seqnr):
                                return ackresp
                        elif (len(msg) == 38 and msg[0:1] == b'\x05') or(len(msg) == 39 and msg[0:1] == b'\x83'):
                            ackresp = PlugwiseAckMacResponse()
                            ackresp.unserialize(msg)
                            if self.is_in_sequence(ackresp, seqnr):
                                return ackresp
                        else:
                            #it does not appear to be a proper Ack message
                            #just retry to read next message
                            logcomm("RERR %4d %s - <!> unexpected response error: %s" % ( len(msg), logf(msg), str(reason)))
                        # except ProtocolError as reason:
                        #     #retry to receive the response
                        #     logcomm("RERR %4d %s - <!> protocol error while interpreting as Ack: %s" % ( len(msg), logf(msg), str(reason)))
                        #     error("protocol error [3]:"+str(reason))
                        # except OutOfSequenceException as reason:
                        #     #retry to receive the response
                        #     #test ping response any offline circle
                        #     if resp.function_code == '000E':
                        #         info("expect_response while interpreting as Ack: out of sequence ping response")
                        #         pingresp = PlugwisePingResponse()
                        #         pingresp.unserialize(msg)
                        #         circle = self.circles[resp.mac]
                        #         circle.pong = True
                        #     else:
                        #         logcomm("RERR %4d %s - <!> out of sequence while interpreting as Ack: %s" % ( len(msg), logf(msg), str(reason)))
                        #         error("protocol error [4]:"+str(reason))
                        # except UnexpectedResponse as reason:
                        #     #response could be an error status message
                        #     logcomm("RERR %4d %s - <!> unexpected response error while interpreting as Ack: %s" % ( len(msg), logf(msg), str(reason)))
                        #     error("unexpected response [2]:"+str(reason))
                    elif resp.function_code == b'0006':
                        info("entering unknown advertise MAC [2]")
                        ackresp = PlugwiseAdvertiseNodeResponse()
                        ackresp.unserialize(msg)
                        info("[0006 with in-sequence?] unknown advertise MAC [2] %s" % logf(ackresp.mac))
                        if ackresp.mac not in self.unjoined:
                            self.unjoined.add(ackresp.mac)
                    elif resp.function_code == b'0061':
                        ackresp = PlugwiseAckAssociationResponse()
                        ackresp.unserialize(msg)
                        info("[0061 with in-sequence?] unknown MAC associating [2] %s" % logf(ackresp.mac))
                    else:
                        logcomm("RERR %4d %s - <!> unexpected response error while expecting Ack: %s" % ( len(msg), logf(msg), str(reason)))                    
                        error("unexpected response [4]:"+str(reason))
                #Reinterpretation of response should never raise ProtocolError or UnexpectedResponse
                #OutOfSequenceException is suppressed bu not passing seqnr in Response constructor
                except (OutOfSequenceException, ProtocolError, UnexpectedResponse) as reason:
                    #retry to receive the response
                    logcomm("RERR %4d %s - <!> error while reinterpreting unexpected response: %s" % ( len(msg), logf(msg), str(reason)))
                    error("error while reinterpreting  unexpected response:"+str(reason))
            error("TEST: %s - going to retry receive msg" % (logf(resp.function_code),))


    def enable_joining(self, enabled):
        req = PlugwiseEnableJoiningRequest(b'', enabled)
        _, seqnr  = self.send_msg(req.serialize())
        self.expect_response(PlugwiseAckMacResponse)

    def join_node(self, newmac, permission):
        req = PlugwiseJoinNodeRequest(newmac.encode('utf-8'), permission)
        _, seqnr  = self.send_msg(req.serialize())
        #No response other then normal ack
        #After this an unsollicted 0061 response from the circle may be received.

    def reset(self):
        type = 0
        req = PlugwiseResetRequest(self._mac(), self._devtype, 20)
        _, seqnr  = self.send_msg(req.serialize())
        resp = self.expect_response(PlugwiseAckMacResponse)
        return resp.status.value

    def status(self):
        req = PlugwiseStatusRequest()
        _, seqnr  = self.send_msg(req.serialize())
        #TODO: There is a short and a long response to 0011.
        #The short reponse occurs when no cirlceplus is connected, and has two byte parameters.
        #The short repsonse is likely not properly handled (exception?)
        resp = self.expect_response(PlugwiseStatusResponse)
        debug(str(resp))
        self.mac = resp.mac.decode('utf-8')
        if resp.network_id !=  0:
            self.pan = resp.network_id.serialize()
            self.short_pan = resp.network_id_short.serialize()
            self.circleplusmac = b'00'+resp.network_id.serialize()[2:]
        return resp.network_is_online
        
    def find_circleplus(self):
        req = PlugwiseQueryCirclePlusRequest()
        _, seqnr  = self.send_msg(req.serialize())
        #Receive the circle+ response, but possibly, only an end-protocol response is seen.
        success = False
        try:
            resp = self.expect_response(PlugwiseQueryCirclePlusResponse)
            success=True
            self.circleplusmac = resp.new_node_mac_id.serialize()
        except (TimeoutException, SerialException) as reason:
            error("Error: %s, %s" % (datetime.datetime.now().isoformat(), str(reason),))        
        return success

    def connect_circleplus(self):
        req = PlugwiseConnectCirclePlusRequest(self.circleplusmac)
        _, seqnr  = self.send_msg(req.serialize())
        resp = self.expect_response(PlugwiseConnectCirclePlusResponse)
        return resp.existing.value, self.allowed.value        
        
class Circle(object):
    """provides interface to the Plugwise Plug & Plug+ devices
    """

    def __init__(self, mac, comchan, attr=None):
        """
        will raise ValueError if mac doesn't look valid
        """
        self.mac = mac.upper()
        if self._validate_mac(mac) == False:
            raise ValueError("MAC address is in unexpected format: "+str(mac))

        self._comchan = comchan
        comchan.circles[self.mac] = self
        
        #self.attr = attr
        #Fix 'swedish' characters
        # self.name = self.name.encode('utf-8')
        # self.name = self.name.encode('utf-8').decode()
        self.name = attr['name'].strip()
        self.always_on = attr['always_on'].strip()
        self.location = attr['location'].strip()
        self.reverse_pol = attr['reverse_pol']
        self.production = attr['production']
        self.loginterval = int(attr['loginterval'].strip())


        self._devtype = None

        self.gain_a = None
        self.gain_b = None
        self.off_noise = None
        self.off_tot = None
        
        self.scheduleCRC = None
        self.schedule = None
        
        self.joined = False
        self.online = False
        self.online_changed = False
        self.pong = False
        self.initialized = False
        self.relay_state = '?'
        self.switch_state = '?'
        self.schedule_state = '?'
        self.requid = 'unset'
        if self.always_on != 'False':
            #self.relay_state = 'on'
            self.schedule_state = 'off'
        self.last_seen = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
        self.last_log = 0
        self.last_log_idx = 0
        self.last_log_ts = 0
        self.cum_energy = 0
        
        self.power = [0, 0, 0, 0]
        self.power_ts = 0
        
        self.interval=60
        self.usage=True
        self.production=False
        
        self.reinit()
        
    def _mac(self):
        #convert mac to bytes for communication protocol
        return self.mac.encode()

    def set_online(self):
        self.online = True
        self.online_changed = True
        self.pong = False

    def reinit(self):
        try:
            info = self.get_info()
            cur_idx = info['last_logaddr']
            self._get_interval(cur_idx)
            if self.always_on != 'False' and self.relay_state == 'off':
                self.switchon()
            #TODO: Check this. Previously log_interval was only set when difference between config file and circle state
            self.set_log_interval(self.loginterval, self.production)
            self.online = True
            self.online_changed = True
            self.initialized = True
        except (ValueError, TimeoutException, SerialException, AttributeError) as reason:
            self.online = False
            self.online_changed = True
            self.initialized = False
            error("OFFLINE Circle '%s' during initialization Error: %s" % (self.name, str(reason)))       
        self.pong = False

    def get_status(self):
        retd = {}
        retd["mac"] = self.mac
        if self._devtype is None:
            retd["type"] = "unknown"
        else:
            retd["type"] = self._devtype
        retd["name"] = self.name
        retd["location"] = self.location
        retd["online"] = self.online
        retd["lastseen"] = self.last_seen
        retd["readonly"] = (self.always_on != 'False')
        retd["reverse_pol"] = (self.reverse_pol != 'False')
        retd["switch"] = self.relay_state
        retd["switchreq"] = self.switch_state
        retd["schedule"] = self.schedule_state
        retd["requid"] = self.requid
        if self.schedule != None:
            retd["schedname"] = self.schedule.name
        else:
            retd["schedname"] = ""
        now = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
        tdelta = now - self.power_ts
        # if tdelta < 60:
            # retd["power"] = self.power[1] # 8-seconds value
        # elif tdelta < 10800:
            # retd["power"] = self.power[2] - self.power[3] # 1 hour value value
        # else:
            # retd["power"] = 0 # clear value
        retd["power1s"] = round(self.power[0], 3)
        retd["power8s"] = round(self.power[1], 3)
        retd["power1h"] = round(self.power[2] - self.power[3], 3)
        retd["powerts"] = self.power_ts
        retd["production"] = self.production
        retd["interval"] = self.interval
        return retd          
           
    def dump_status(self):
        retd = {}
        for key in dir(self):
            ptr = getattr(self, key)
            if key == 'schedule' and not ptr == None:
                retd[key] = ptr.dump_status()
                continue
            #if isinstance(ptr, int):
            if not hasattr(ptr, '__call__') and not key[0] == '_':
                retd[key] = ptr
        return retd          
            
    def _validate_mac(self, mac):
        if not re.match("^[A-F0-9]+$", mac):
            return False

        try:
            _ = int(mac, 16)
        except ValueError:
            return False

        return True

    def _expect_response(self, response_class, seqnr):        
        retry_count = 1
        retry_timeout = 5 #allow 5+1 seconds for timeout
        #instead of expected response a status message with correct seqnr may be received
        #the common case is the offline status 'E1'
        #it appears that in case of bad networks the expected response competes with
        #the offline status. Sometimes the proper response arrives just (<1s) after
        #the offline status.
        #the while loop is intended to deal with this situation.
        while retry_count >= 0:
            retry_count -= 1
            try:
                resp = self._comchan.expect_response(response_class, self._mac(), seqnr, retry_timeout)
            except (TimeoutException, SerialException) as reason:
                if self.online:
                    info("OFFLINE Circle '%s'." % (self.name,))
                self.online = False
                self.online_changed = True
                self.pong = False
                raise TimeoutException("Timeout while waiting for response from circle '%s'" % (self.name,))
            
            # if not isinstance(resp, response_class):
                # #error status returned
                # if resp.status.value == 0xE1:
                    # debug("Received an error status '%04X' from circle '%s' - Network slow or circle offline - Retry receive ..." % (resp.status.value, self.name))
                    # retry_timeout = 1 #allow 1+1 seconds for timeout after an E1.
                # else:
                    # error("Received an error status '%04X' from circle '%s' with correct seqnr - Retry receive ..." % (resp.status.value, self.name))
            if not isinstance(resp, response_class):
                #error status returned
                if resp.status.value == 0xE1:
                    debug("Received an error status '%04X' from circle '%s' - Network slow or circle offline - Retry receive ..." % (resp.status.value, self.name))
                    #retry_timeout = 1 #allow 1+1 seconds for timeout after an E1.
                    if self.online:
                        info("OFFLINE Circle '%s'." % (self.name,))
                    self.online = False
                    self.online_changed = True
                    self.pong = False
                    raise TimeoutException("Timeout while waiting for response from circle '%s'" % (self.name,))
                else:
                    error("Received an error status '%04X' from circle '%s' with correct seqnr - Retry receive ..." % (resp.status.value, self.name))
            else:
                ts_now = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
                if not self.online:
                    info("ONLINE  Circle '%s' after %d seconds." % (self.name, ts_now - self.last_seen))
                    self.online = True
                    self.online_changed = True
                    self.pong = False
                #self.last_seen = (datetime.datetime.utcnow()-datetime.timedelta(seconds=time.timezone)).isoformat()
                self.last_seen = ts_now
                return resp
        #we only end here when multiple ack or ackmac messages are generated before the real response
        if self.online:
            info("OFFLINE Circle '%s'." % (self.name,))
        self.online = False
        self.online_changed = True
        self.pong = False
        #TODO: Replace timeout exception by more specific exception
        raise TimeoutException("Received multiple error messages from circle '%s'" % (self.name,))
        
    def map_type(self, devtype):
        types = dict({0: 'stick', 1: 'circle+', 2: 'circle'})
        return types[devtype]

    def _type(self):
        if self._devtype is None:
            self.get_info()
        return self._devtype
            
    def type(self):
        return self.map_type(self._type())
            
    def pulse_correction(self, pulses, seconds=1):
        """correct pulse count with Circle specific calibration offsets
        @param pulses: pulse counter
        @param seconds: over how many seconds were the pulses counted
        """
        debug("PULSE: uncorrected: %.3f" % (pulses,))
        if pulses == 0:
            return 0.0

        if self.gain_a is None:
            self.calibrate()

        pulses /= float(seconds)
        corrected_pulses = seconds * (((((pulses + self.off_noise)**2) * self.gain_b) + ((pulses + self.off_noise) * self.gain_a)) + self.off_tot)
        debug("PULSE:   corrected: %.3f" % (pulses/seconds,))
        debug("PULSE: t corrected: %.3f" % (pulses,))
        if (pulses > 0.0 and corrected_pulses < 0.0 or pulses < 0.0 and corrected_pulses > 0.0):
            return 0.0
        return corrected_pulses

    def pulses_to_kWs(self, pulses):
        """converts the pulse count to kWs
        """
        # pulses -> kWs
        kWs = pulses/PULSES_PER_KW_SECOND
        return kWs
        
    def watt_to_pulses(self, watt, seconds=1):
        """correct pulse count with Circle specific calibration offsets
        @param watt: power in watts to convert to pulses
        @param seconds: over how many seconds will the pulses be counted
        """
        if watt == 0:
            return 0.0

        if self.gain_a is None:
            self.calibrate()

        corr_pulses_1s = watt * PULSES_PER_KW_SECOND / 1000.0
        
        raw_pulses_1s = (math.sqrt(self.gain_a**2.0 + 4.0 * self.gain_b * (corr_pulses_1s - self.off_tot)) - self.gain_a - 2.0 * self.gain_b * self.off_noise) / (2.0 * self.gain_b);
        if (corr_pulses_1s > 0.0 and raw_pulses_1s < 0.0 or corr_pulses_1s < 0.0 and raw_pulses_1s > 0.0):
            return 0.0
        return seconds*raw_pulses_1s

    def calibrate(self):
        """fetch calibration info from the device
        """
        msg = PlugwiseCalibrationRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        calibration_response = self._expect_response(PlugwiseCalibrationResponse, seqnr)
        retl = []

        for x in ('gain_a', 'gain_b', 'off_noise', 'off_tot'):
            val = getattr(calibration_response, x).value
            retl.append(val)
            setattr(self, x, val)

        return retl

    def get_pulse_counters(self):
        """return pulse counters for 1s interval, 8s interval and for the current hour,
        both usage and production as a tuple
        """
        msg = PlugwisePowerUsageRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        debug("counters mac %s, seqnr %s" % (self.mac, seqnr))
        resp = self._expect_response(PlugwisePowerUsageResponse, seqnr)
        p1s, p8s, p1h, pp1h = resp.pulse_1s.value, resp.pulse_8s.value, resp.pulse_hour.value, resp.pulse_prod_hour.value
        if self.production == 'False':
            pp1h = 0
        return (p1s, p8s, p1h, pp1h)

    def get_power_usage(self):
        """returns power usage for the last second in Watts
        might raise ValueError if reading the pulse counters fails
        """
        pulse_1s, pulse_8s, pulse_1h, pulse_prod_1h = self.get_pulse_counters()
        kw_1s = 1000*self.pulses_to_kWs(self.pulse_correction(pulse_1s))
        debug("POWER:          1s: %.3f" % (kw_1s,))
        kw_8s = 1000*self.pulses_to_kWs(self.pulse_correction(pulse_8s, 8))/8.0
        debug("POWER:          8s: %.3f" % (kw_8s,))
        kw_1h = 1000*self.pulses_to_kWs(self.pulse_correction(pulse_1h, 3600))/3600.0
        debug("POWER:          1h: %.3f" % (kw_1h,))
        kw_p_1h = 1000*self.pulses_to_kWs(self.pulse_correction(pulse_prod_1h, 3600))/3600.0
        debug("POWER:     prod 1h: %.3f" % (kw_p_1h,))
        if self.reverse_pol == 'True':
            kw_1s = -kw_1s 
            kw_8s = -kw_8s
            kw_1h = -kw_1h
            kw_p_1h = -kw_p_1h
            debug("get_power_usage: reverse polarity of %s" % (self.mac,))
        self.power = [kw_1s, kw_8s, kw_1h, kw_p_1h]
        self.power_ts = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
        #just return negative values. It is production

        return (kw_1s, kw_8s, kw_1h, kw_p_1h)

    def get_info(self):
        """fetch relay state & current logbuffer index info
        """
        def map_hz(hz_raw):
            if hz_raw == 133:
                return 50
            elif hz_raw == 197:
                return 60
                
        def relay(state):
            states = dict({0: 'off', 1: 'on'})
            return states[state]

        msg = PlugwiseInfoRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseInfoResponse, seqnr)
        retd = response_to_dict(resp)
        retd['hz'] = map_hz(retd['hz'])
        self._devtype = retd['type']
        retd['type'] = self.map_type(retd['type'])
        retd['relay_state'] = relay(retd['relay_state'])
        self.relay_state = retd['relay_state']
        return retd

    def get_clock(self):
        """fetch current time from the device
        """
        msg = PlugwiseClockInfoRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseClockInfoResponse, seqnr)
        self.scheduleCRC = resp.scheduleCRC.value
        debug("Circle %s get clock to %s" % (self.name, resp.time.value.isoformat()))
        return resp.time.value

    def set_clock(self, dt):
        """set clock to the value indicated by the datetime object dt
        """
        debug("Circle %s set clock to %s" % (self.name, dt.isoformat()))
        msg = PlugwiseClockSetRequest(self._mac(), dt).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseAckMacResponse, seqnr)
        #status = '00D7'
        return dt

    def switch(self, on):
        """switch power on or off
        @param on: new state, boolean
        """
        info("API  %s %s circle switch: %s" % (self.mac, self.name, 'on' if on else 'off',))
        if not isinstance(on, bool):
            return False
        if self.always_on != 'False' and on != True:
            return False
        req = PlugwiseSwitchRequest(self._mac(), on)
        _, seqnr  = self._comchan.send_msg(req.serialize())
        resp = self._expect_response(PlugwiseAckMacResponse, seqnr)
        if on == True:
            if resp.status.value != 0xD8:
                error("Wrong switch status reply when  switching on. expected '00D8', received '%04X'" % (resp.status.value,))
            self.switch_state = 'on'
            self.relay_state = 'on'
            #self.schedule_state = 'off'
        else:
            if resp.status.value != 0xDE:
                error("Wrong switch status reply when switching off. expected '00DE', received '%04X'" % (resp.status.value,))
            self.switch_state = 'off'
            self.relay_state = 'off'
            #self.schedule_state = 'off'
        return 

    def switch_on(self):
        self.switch(True)
        #status = '00D8'

    def switch_off(self):
        self.switch(False)
        #status = '00DE'

    def get_power_usage_history(self, log_buffer_index=None, start_dt=None):
        """Reads power usage information from the given log buffer address at the Circle.
        Each log buffer contains the power usage data for 4 intervals, some of which might
        not be filled yet. The intervals can contain values for usage, or values for both
        usage and production. Production values are negative, and have the same timestamp
        as their preceding usage value. The default is usage only with a 3600 sec = 1 hour
        interval. The interval and production can be set with set_log_interval().
        
        @param log_buffer_index: index of the first log buffer to return.
            If None then current log buffer index is used
        @return: list of (datetime|None, average-watt-in-interval, watt-hours-in-this-interval)
            tuples.
            If the first tuple element is None it means this buffer isn't written yet and
            the second and third value are undefined in that case.
        """

        if log_buffer_index is None:
            info_resp = self.get_info()
            log_buffer_index = info_resp['last_logaddr']
            #the cur-pos may not be complete.
            if log_buffer_index > 0:
                log_buffer_index -= 1

        log_req = PlugwisePowerBufferRequest(self._mac(), log_buffer_index).serialize()
        _, seqnr  = self._comchan.send_msg(log_req)
        resp = self._expect_response(PlugwisePowerBufferResponse, seqnr)
        
        intervals = []
        dts = []
        pulses = []
        
        if start_dt is None:
            prev_dt = getattr(resp, "logdate1").value
        else:
            prev_dt = start_dt
        if prev_dt is None:
            error("get_power_usage_history: empty first entry in power buffer")
            return []
        prev2_dt = prev_dt
        #both = False
        for i in range(0, 4):
            dt = getattr(resp, "logdate%d" % (i+1,)).value
            if not dt is None:
                dts.append(dt)
                pulses.append(getattr(resp, "pulses%d" % (i+1,)).value)
                if prev_dt == dts[i]:
                    #both = True
                    intervals.append((dts[i]-prev2_dt).total_seconds())
                else:
                    intervals.append((dts[i]-prev_dt).total_seconds())               
                prev2_dt = prev_dt
                prev_dt = dts[i]

        retl = []        
        for i in range(0, len(dts)):
            #first two elements of interval may be zero. Derive intervals
            #try to get it from intervals within the four readings
            #otherwise assume 60 minutes.
            if intervals[i] == 0:
                if len(dts)>i+1 and dts[i] == dts[i+1]:
                    if len(dts)>i+2:
                        intervals[i] = (dts[i+2]-dts[i]).total_seconds()                        
                    else:
                        intervals[i]=3600
                elif len(dts)>i+1:  
                    intervals[i] = (dts[i+1]-dts[i]).total_seconds()
                else:
                    intervals[i]=3600
                if intervals[i] == 0:
                    #can occur when time syncing the circle sets time some seconds back.
                    error("get_power_usage_history: all four intervals having same timestamp. set interval=60")
                    error("get_power_usage_history: dts %s" % dts)
                    error("get_power_usage_history: pulses %s" % pulses)
                    intervals[i] = 60
               
            corrected_pulses = self.pulse_correction(pulses[i], intervals[i])
            watt = self.pulses_to_kWs(corrected_pulses)/intervals[i]*1000
            watthour = self.pulses_to_kWs(corrected_pulses)/3600*1000
            if self.reverse_pol == 'True':
                watt = -watt 
                watthour = -watthour
                debug("get_power_usage_history: reverse polarity of %s" % (self.mac,))

            retl.append((dts[i], watt, watthour))
        return retl

    def get_power_usage_history_raw(self, log_buffer_index=None):
        """Reads the raw interpreted power usage information from the given log buffer 
        address at the Circle. This function reads (check!) 64 bytes of memory.
        The function can be used to make a total memory dump of the circle, as increasing
        addresses causes a wrap around.

        @param log_buffer_index: index of the first log buffer to return.
            If None then current log buffer index is used
        @return: list of hexadecimal (single string?) bytes
        """

        if log_buffer_index is None:
            info_resp = self.get_info()
            log_buffer_index = info_resp['last_logaddr']

        log_req = PlugwisePowerBufferRequest(self._mac(), log_buffer_index).serialize()
        _, seqnr  = self._comchan.send_msg(log_req)
        resp = self._expect_response(PlugwisePowerBufferResponseRaw, seqnr)
        retl = getattr(resp, "raw").value

        return retl

    def set_log_interval(self, interval, production=False):
        """set log interval in minutes for usage and production
        
        @param interval: the loginterval in minutes.
        @param production: boolean to indicate logging for production.        
            False: Usage logging only.
            True:  Usage and Production logging.
        """
        msg = PlugwiseLogIntervalRequest(self._mac(), interval, interval if production else 0).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        return self._expect_response(PlugwiseAckMacResponse, seqnr)
        #status = '00F8'
        
    def get_features(self):
        """fetch feature set
        """

        msg = PlugwiseFeatureSetRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseFeatureSetResponse, seqnr)
        return resp.features.value
        
    def get_circleplus_datetime(self):
        """fetch current time from the circle+
        """
        msg = PlugwiseDateTimeInfoRequest(self._mac()).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseDateTimeInfoResponse, seqnr)
        dt = datetime.datetime.combine(resp.date.value, resp.time.value)
        return dt
        
    def set_circleplus_datetime(self, dt):
        """set circle+ clock to the value indicated by the datetime object dt
        """
        msg = PlugwiseSetDateTimeRequest(self._mac(), dt).serialize()
        _, seqnr  = self._comchan.send_msg(msg)
        return self._expect_response(PlugwiseAckMacResponse, seqnr)
        #status = '00DF'=ack '00E7'=nack
        
    def define_schedule(self, name, scheddata, dst=0):
        info("circle.define_schedule.")
        self.schedule = Schedule(name, scheddata, self.watt_to_pulses)
        self.schedule._dst_shift(dst)

    def undefine_schedule(self):
        self.schedule = None

    def load_schedule(self, dst=0):
        if not self.schedule._pulse is None:
            info("circle.load_schedule. enter function")
            self.schedule._dst_shift(dst)
            #TODO: add test on inequality of CRC
            
            #info("schedule %s" % self.schedule._pulse)
            for idx in range(0,84):
                chunk = self.schedule._pulse[(8*idx):(8*idx+8)]
                req = PlugwisePrepareScheduleRequest(idx, chunk)
                _, seqnr  = self._comchan.send_msg(req.serialize())
            for idx in range(1,43):
                req = PlugwiseSendScheduleRequest(self._mac(), idx)
                _, seqnr  = self._comchan.send_msg(req.serialize())
                resp = self._expect_response(PlugwiseSendScheduleResponse, seqnr)
            info("circle.load_schedule. exit function")

    def schedule_onoff(self, on):
        """switch schedule on or off
        @param on: new state, boolean
        """
        info("API  %s %s circle schedule %s" % (self.mac, self.name, 'on' if on else 'off'))
        if not isinstance(on, bool):
            return False
        if self.always_on != 'False':
            return False
        req = PlugwiseEnableScheduleRequest(self._mac(), on)
        _, seqnr  = self._comchan.send_msg(req.serialize())
        resp = self._expect_response(PlugwiseAckMacResponse, seqnr)
        if on == True:
            if resp.status.value != 0xE4:
                error("Wrong schedule status reply when setting schedule on. expected '00E4', received '%04X'" % (resp.status.value,))
            self.schedule_state = 'on'
            #update self.relay_state
            self.get_info()
        else:
            if resp.status.value != 0xE5:
                error("Wrong schedule status reply when setting schedule off. expected '00E5', received '%04X'" % (resp.status.value,))
            self.schedule_state = 'off'  
        return 

    def schedule_on(self):
        self.schedule_onoff(True)
        #status = '00E4'

    def schedule_off(self):
        self.schedule_onoff(False)
        #status = '00E5'

    def set_schedule_value(self, val):
        """Set complete schedule to a single value.
        @param val: -1=On 0=Off >0=StandbyKiller threshold in Watt
        """
        #TODO: incorporate this in Schedule object
        val = self.watt_to_pulses(val) if val>=0 else val
        req = PlugwiseSetScheduleValueRequest(self._mac(), val)
        _, seqnr  = self._comchan.send_msg(req.serialize())
        return self._expect_response(PlugwiseAckMacResponse, seqnr)
        #status = '00FA'
        
        
    def _get_interval(self, cur_idx):
        self.interval=60
        self.usage=True
        self.production=False
        if cur_idx < 1:
            return
        log = self.get_power_usage_history(cur_idx)
        if len(log)<3:
            log = self.get_power_usage_history(cur_idx-1) + log
        if len(log)<3:
            error("_get_interval: to few entries in power buffer to determine interval")
            return
        #debug(log)
        interval = log[-1][0]-log[-2][0]
        self.usage=True
        if interval == timedelta(0):
            interval = log[-1][0]-log[-3][0]
            self.production=True
        self.interval = int(interval.total_seconds())/60
        
    def ping(self):
        """ping circle
        """
        req = PlugwisePingRequest(self._mac())
        _, seqnr  = self._comchan.send_msg(req.serialize())
        debug("pinged mac %s, seqnr %s" % (self.mac, seqnr))
        return #self._expect_response(PlugwisePingResponse, seqnr)

    def ping_synchronous(self):
        """ping circle
        """
        req = PlugwisePingRequest(self._mac())
        _, seqnr  = self._comchan.send_msg(req.serialize())
        return self._expect_response(PlugwisePingResponse, seqnr)

    def read_node_table(self):
        #Needs to be called on Circle+
        nodetable = []
        for idx in range(0,64):
            req = PlugwiseAssociatedNodesRequest(self._mac(), idx)
            _, seqnr  = self._comchan.send_msg(req.serialize())
            resp = self._expect_response(PlugwiseAssociatedNodesResponse, seqnr)
            nodetable.append(resp.node_mac_id.value)
        return nodetable
        
    def remove_node(self, removemac):
        #Needs to be called on Circle+
        req = PlugwiseRemoveNodeRequest(self._mac(), removemac)
        _, seqnr  = self._comchan.send_msg(req.serialize())
        resp = self._expect_response(PlugwiseRemoveNodeResponse, seqnr)
        return resp.status.value
            
    def reset(self):
        req = PlugwiseResetRequest(self._mac(), self._type(), 20)
        _, seqnr  = self._comchan.send_msg(req.serialize())
        resp = self._expect_response(PlugwiseAckMacResponse, seqnr)
        return resp.status.value
            
def response_to_dict(r):
    retd = {}
    for key in dir(r):
        ptr = getattr(r, key)
        if isinstance(ptr, BaseType):
            retd[key] = ptr.value
    return retd

class Schedule(object):
    """Schedule for circles(+) to control timed On/Off/StandByKiller
    A value per 15 minutes 24/7, 672 values (int) in total
    -1 = On
    0  = Off
    >0 = StandbyKiller threshold in Watt
    The objects can exist meaningful in the context of a circle only, as 
    calibration data is required for conversion to pulses and CRC calculation
    """
    
    def __init__(self, name, scheddata, circle_w2p):
        """
        ......
        """
        self.name = str(name)
        self.dst = 0
        self._watt = scheddata
        self._pulse = list(int(self.watt_to_pulses(circle_w2p, w)) if w>0 else w for w in self._watt)
        #self._pulse = list(int(circle_w2p(i)) if i>0 else i for i in self._watt)
        #self._shift_day()
        self.CRC = crc_fun(''.join(str(struct.pack('>h',i)) for i in self._pulse))
        #self._hex = ''.join(("%04X" % int_to_uint(i,4)) for i in self._pulse)
        
    def watt_to_pulses(self, circle_w2p, watt):
        #minimize at one pulse when watts is around 3 or lower.
        pulses = circle_w2p(watt)
        return pulses if pulses > 0 else 1

    def dump_status(self):
        retd = {}
        retd['name'] = self.name
        retd['CRC'] = self.CRC
        retd['schedule'] = self._watt
        return retd
        
    # def _shift_day(self):
        # info("circle.schedule._shift_day rotate left by one day")
        # #rotate schedule a day to the left
        # self._pulse = self._pulse[96:]+self._pulse[:96]
        # #self.CRC = crc_fun(''.join(str(struct.pack('>h',i)) for i in self._pulse))

    def _dst_shift(self, dst):
        if self.dst and not dst:
            info("circle.schedule._dst_shift rotate right [end of DST]")
            #rotate schedule 4 quarters right (forward in time)
            self._pulse = self._pulse[-4:]+self._pulse[:-4]
            self.CRC = crc_fun(''.join(str(struct.pack('>h',i)) for i in self._pulse))
            self.dst = 0
        elif not self.dst and dst:
            info("circle.schedule._dst_shift rotate left [start of DST]")
            #rotate schedule 4 quarters left (backward in time)
            self._pulse = self._pulse[4:]+self._pulse[:4]
            self.CRC = crc_fun(''.join(str(struct.pack('>h',i)) for i in self._pulse))
            self.dst = 1
