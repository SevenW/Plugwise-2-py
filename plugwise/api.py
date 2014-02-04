#!/bin/env python

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

# TODO:
#   - implement reading energy usage history from the buffer inside Circle
#   - make communication channel concurrency safe
#   - return more reasonable responses than response message objects from the functions that don't do so yet
#   - make message construction syntax better. Fields should only be specified once and contain name so we can serialize response message to dict
#   - verify response checksums
#   - look at the ACK messages
#   - unit tests
#   - pairing
#   - switching schedule upload
#   - support for older firmware versions

import re
import sys
import time

from .util import *
from .protocol import *
from .exceptions import *

PULSES_PER_KW_SECOND = 468.9385193

DEFAULT_TIMEOUT = 10

class Stick(SerialComChannel):
    """provides interface to the Plugwise Stick"""

    def __init__(self, port=0, timeout=DEFAULT_TIMEOUT):
        SerialComChannel.__init__(self, port=port, timeout=timeout)
        self.init()

    def init(self):
        """send init message to the stick"""
        msg = PlugwiseInitRequest().serialize()
        self.send_msg(msg)
        resp = self.expect_response(PlugwiseInitResponse)
        debug(str(resp))

    def send_msg(self, cmd):
        debug("_send_cmd:"+repr(cmd))
        self.write(cmd)

    def _recv_response(self, response_obj):
        readlen = len(response_obj)
        debug("expecting to read "+str(readlen)+" bytes for msg. "+str(response_obj))
        msg = self.readline()
        if msg == b"":
            raise TimeoutException("Timeout while waiting for response from device")

        debug("read:"+repr(msg)+" with length "+str(len(msg)))

        header_start = msg.find(PlugwiseMessage.PACKET_HEADER)
        if header_start > 0:
            # 2011 firmware seems to sometimes send extra \x83 byte before some of the
            # response messages but there might a all kinds of chatter going on so just 
            # look for our packet header
            msg = msg[header_start:]

        response_obj.unserialize(msg)
        return response_obj

    def expect_response(self, response_class, src_mac=None):
        resp = response_class()
        # XXX: there's a lot of debug info flowing on the bus so it's
        # expected that we constantly get unexpected messages
        while 1:
            try:
                retval = self._recv_response(resp)

                if src_mac is None or src_mac == retval.mac:
                    return retval

            except ProtocolError as reason:
                error("encountered protocol error:"+str(reason))

class Circle(object):
    """provides interface to the Plugwise Plug & Plug+ devices
    """

    def __init__(self, mac, comchan):
        """
        will raise ValueError if mac doesn't look valid
        """
        mac = mac.upper()
        if self._validate_mac(mac) == False:
            raise ValueError("MAC address is in unexpected format: "+str(mac))

        self.mac = sc(mac)

        self._comchan = comchan

        self.gain_a = None
        self.gain_b = None
        self.off_ruis = None
        self.off_tot = None

    def _validate_mac(self, mac):
        if not re.match("^[A-F0-9]+$", mac):
            return False

        try:
            _ = int(mac, 16)
        except ValueError:
            return False

        return True

    def _expect_response(self, response_class):
        return self._comchan.expect_response(response_class, self.mac)

    def pulse_correction(self, pulses, seconds=1):
        """correct pulse count with Circle specific calibration offsets
        @param pulses: pulse counter
        @param seconds: over how many seconds were the pulses counted
        """
        if pulses == 0:
            return 0.0

        if self.gain_a is None:
            self.calibrate()

        pulses /= float(seconds)
        corrected_pulses = seconds * (((((pulses + self.off_ruis)**2) * self.gain_b) + ((pulses + self.off_ruis) * self.gain_a)) + self.off_tot)
        return corrected_pulses

    def pulses_to_kWs(self, pulses):
        """converts the pulse count to kWs
        """
        # pulses -> kWs
        kWs = pulses/PULSES_PER_KW_SECOND
        return kWs

    def calibrate(self):
        """fetch calibration info from the device
        """
        msg = PlugwiseCalibrationRequest(self.mac).serialize()
        self._comchan.send_msg(msg)
        calibration_response = self._expect_response(PlugwiseCalibrationResponse)
        retl = []

        for x in ('gain_a', 'gain_b', 'off_ruis', 'off_tot'):
            val = getattr(calibration_response, x).value
            retl.append(val)
            setattr(self, x, val)

        return retl

    def get_pulse_counters(self):
        """return pulse counters for 1s interval, 8s interval and for the current hour
        as a tuple
        """
        msg = PlugwisePowerUsageRequest(self.mac).serialize()
        self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwisePowerUsageResponse)
        p1s, p8s, p1h = resp.pulse_1s.value, resp.pulse_8s.value, resp.pulse_hour.value

        # sometimes the circle returns max values for some of the pulse counters
        # I have no idea what it means but it certainly isn't a reasonable value
        # so I just assume that it's meant to signal some kind of a temporary error condition
        if p1s == 65535 or p8s == 65535:
            raise ValueError("Pulse counters seem to contain unreasonable values")
        if p1h == 4294967295:
            raise ValueError("1h pulse counter seems to contain an unreasonable value")

        return (p1s, p8s, p1h)

    def get_power_usage(self):
        """returns power usage for the last second in Watts
        might raise ValueError if reading the pulse counters fails
        """
        pulse_1s, _, _ = self.get_pulse_counters()
        corrected_pulses = self.pulse_correction(pulse_1s)
        retval = self.pulses_to_kWs(corrected_pulses)*1000
        # sometimes it's slightly less than 0, probably caused by calibration/calculation errors
        # it doesn't make much sense to return negative power usage in that case
        return retval if retval > 0.0 else 0.0

    def get_info(self):
        """fetch relay state & current logbuffer index info
        """
        def map_hz(hz_raw):
            if hz_raw == 133:
                return 50
            elif hz_raw == 197:
                return 60

        msg = PlugwiseInfoRequest(self.mac).serialize()
        self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseInfoResponse)
        retd = response_to_dict(resp)
        retd['hz'] = map_hz(retd['hz'])
        return retd

    def get_clock(self):
        """fetch current time from the device
        """
        msg = PlugwiseClockInfoRequest(self.mac).serialize()
        self._comchan.send_msg(msg)
        resp = self._expect_response(PlugwiseClockInfoResponse)
        return resp.time.value

    def set_clock(self, dt):
        """set clock to the value indicated by the datetime object dt
        """
        msg = PlugwiseClockSetRequest(self.mac, dt).serialize()
        self._comchan.send_msg(msg)
        return dt

    def switch(self, on):
        """switch power on or off
        @param on: new state, boolean
        """
        req = PlugwiseSwitchRequest(self.mac, on)
        return self._comchan.send_msg(req.serialize())

    def switch_on(self):
        self.switch(True)

    def switch_off(self):
        self.switch(False)

    def get_power_usage_history(self, log_buffer_index=None):
        """Reads power usage information from the given log buffer address at the Circle.
        Each log buffer contains the power usage data for 4 hours, some of which might not be filled yet.

        @param log_buffer_index: index of the first log buffer to return.
            If None then current log buffer index is used
        @return: list of (datetime | None, watt-hours-used-in-this-hour) tuples
            If the first tuple element is None it means this buffer isn't written yet and the second value
            is undefined in that case.
        """

        if log_buffer_index is None:
            info_resp = self.get_info()
            log_buffer_index = info_resp['last_logaddr']

        log_req = PlugwisePowerBufferRequest(self.mac, log_buffer_index).serialize()
        self._comchan.send_msg(log_req)
        resp = self._expect_response(PlugwisePowerBufferResponse)
        retl = []

        for i in range(1, 5):
            dt = getattr(resp, "logdate%d" % (i,)).value
            corrected_pulses = self.pulse_correction(getattr(resp, "pulses%d" % (i,)).value, 3600)
            watts = self.pulses_to_kWs(corrected_pulses)/3600*1000
            retl.append((dt, watts))

        return retl

def response_to_dict(r):
    retd = {}
    for key in dir(r):
        ptr = getattr(r, key)
        if isinstance(ptr, BaseType):
            retd[key] = ptr.value
    return retd
