#!/usr/bin/env python3

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

from pprint import pprint
import optparse
import logging

from serial.serialutil import SerialException

from plugwise import *
from swutil.util import *
from plugwise.api import *

log_comm(False)
init_logger("plugwise_util.log")
log_level(logging.INFO)

DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"

#default settings for attr-field of cirle
conf = {"mac": "000D6F0001000000", "category": "misc", "name": "circle_n", "loginterval": "60", "always_on": "False", "production": "False", "reverse_pol": "False", "location": "misc"}

parser = optparse.OptionParser()
parser.add_option("-m", "--mac", dest="mac", help="MAC address")
parser.add_option("-d", "--device", dest="device", 
    help="Serial port device")
parser.add_option("-p", "--power", action="store_true", 
    help="Get current power usage")
parser.add_option("-t", "--time", dest="time",
    help="""Set circle's internal clock to given time. 
Format is 'YYYY-MM-DD hh:mm:ss' use the special value 'sync' if you want to set Circles clock to the same time as your computer""")
parser.add_option("-C", "--counter", action="store_true", 
    help="Print out values of the pulse counters")
parser.add_option("-c", "--continuous", type="int",
    help="Perform the requested action in an endless loop, sleeping for the given number of seconds in between.")
parser.add_option("-s", "--switch", dest="switch", 
    help="Switch power on/off. Possible values: 1,on,0,off")
parser.add_option("-l", "--log", dest="log", 
    help="""Read power usage history from the log buffers of the Circle. 
    Argument should be 'cur' or 'current' if you want to read the log buffer that is currently being written.
    It can also be a numeric log buffer index if you want to read an arbitrary log buffer. 
""")
parser.add_option("-i", "--info", action="store_true", dest="info", 
    help="Perform the info request")
parser.add_option("-q", "--query", dest="query",
    help="""Query data. Possible values are: time, pulses, last_logaddr, relay_state""")
parser.add_option("-v", "--verbose", dest="verbose",
    help="""Verbose mode. Argument should be a number representing verboseness. 
    Currently all the debug is logged at the same level so it doesn't really matter which number you use.""")

options, args = parser.parse_args()

device = DEFAULT_SERIAL_PORT

if options.device:
    device = options.device

if not options.mac:
    print("you have to specify mac with -m")
    parser.print_help()
    sys.exit(-1)

if options.verbose:
    plugwise.util.DEBUG_PROTOCOL = True

def print_pulse_counters(c):
    try:
        print("%d %d %d %d" % c.get_pulse_counters())
    except ValueError:
        print("Error: Failed to read pulse counters")

def handle_query(c, query):
    if query == 'time':
        print(c.get_clock().strftime("%H:%M:%S"))
    elif query == 'pulses':
        print_pulse_counters(c)
    elif query in ('last_logaddr', 'relay_state'):
        print(c.get_info()[query])

def handle_log(c, log_opt):
    if log_opt in ('cur', 'current'):
        log_idx = None
    else:
        try:
            log_idx = int(log_opt)
        except ValueError:
            print("log option argument should be either number or string current")
            return False

    print("power usage log:")
    for dt, watt, watt_hours in c.get_power_usage_history(log_idx):

        if dt is None:
            ts_str, watt, watt_hours = "N/A", "N/A", "N/A"
        else:
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
            watt = "%7.2f" % (watt,)
            watt_hours = "%7.2f" % (watt_hours,)

        print("\t%s %s W %s Wh" % (ts_str, watt, watt_hours))

    return True


def set_time(c, time_opt):
    if time_opt == 'sync':
        set_ts = datetime.datetime.now()
    else:
        try:
            set_ts = datetime.datetime.strptime(time_opt, "%Y-%m-%d %H:%M:%S")
        except ValueError as reason:
            print("Error: Could not parse the time value: %s" % (str(reason),))
            sys.exit(-1)

    c.set_clock(set_ts)

try:
    device = Stick(device)
	
    conf['mac'] = options.mac.upper()
    c = Circle(conf['mac'], device, conf)

    
    if options.time:
        set_time(c, options.time)

    if options.switch:
        sw_direction = options.switch.lower()

        if sw_direction in ('on', '1'):
            c.switch_on()
        elif sw_direction in ('off', '0'):
            c.switch_off()
        else:
            print("Error: Unknown switch direction: "+sw_direction)
            sys.exit(-1)
    
    while 1:
        if options.power:
            try:
                print("power usage: 1s=%7.2f W   8s=%7.2f W   1h=%7.2f W   1h=%7.2f W(production)" % c.get_power_usage())
            except ValueError:
                print("Error: Failed to read power usage")

        if options.log != None:
            handle_log(c, options.log)

        if options.info:
            print("info:")
            pprint(c.get_info())

        if options.counter:
            print_pulse_counters(c)

        if options.query:
            handle_query(c, options.query)

        if options.continuous is None:
            break
        else:
            time.sleep(options.continuous)

except (TimeoutException, SerialException) as reason:
    print("Error: %s" % (reason,))
