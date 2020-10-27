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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Plugwise-2-py. If not, see <http://www.gnu.org/licenses/>. 
#
# The program is a major modification and extension to:
#   python-plugwise - written in 2011 by Sven Petai <hadara@bsd.ee> 
# which itself is inspired by Plugwise-on-Linux (POL):
#   POL v0.2 - written in 2009 by Maarten Damen <http://www.maartendamen.com>

from serial.serialutil import SerialException

from plugwise import *
from swutil.util import *
from swutil.pwmqtt import *
from plugwise.api import *

from datetime import datetime, timedelta
import time
import calendar
import subprocess
import glob
import os
import logging
import queue
import threading
import itertools

mqtt = True
try:
    import paho.mqtt.client as mosquitto
except:
    mqtt = False
print(mqtt)

import pprint as pp
import json

#from json import encoder
#encoder.FLOAT_REPR = lambda o: format(o, '.2f')
json.encoder.FLOAT_REPR = lambda f: ("%.2f" % f)

def jsondefault(object):
    return object.decode('utf-8')

#DEBUG_PROTOCOL = False
log_comm(True)
#LOG_LEVEL = 2

schedules_path = "config/schedules"
cfg = json.load(open("config/pw-hostconfig.json"))
tmppath = cfg['tmp_path']+'/'
perpath = cfg['permanent_path']+'/'
logpath = cfg['log_path']+'/'
port = cfg['serial']
epochf = False
if 'log_format' in cfg and cfg['log_format'] == 'epoch':
    epochf = True
    
actdir = 'pwact/'
actpre = 'pwact-'
actpost = '.log'
curpre = 'pwpower'
curpost = '.log'
logdir = 'pwlog/'
logpre = 'pw-'
logpost = '.log'

open_logcomm(logpath+"pw-communication.log")

#prepare for cleanup of /tmp after n days.
cleanage = 604800; # seven days in seconds

locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
now = locnow
yrfolder = str(now.year)+'/'
if not os.path.exists(perpath+yrfolder+actdir):
    os.makedirs(perpath+yrfolder+actdir)
if not os.path.exists(perpath+yrfolder+logdir):
    os.makedirs(perpath+yrfolder+logdir)
if not os.path.exists(tmppath+yrfolder+actdir):
    os.makedirs(tmppath+yrfolder+actdir)
rsyncing = True
if tmppath == None or tmppath == "/":
    tmppath = perpath
    rsyncing = False
if rsyncing:
    # Could be a recovery after a power failure
    # /tmp/pwact-* may have disappeared, while the persitent version exists
    perfile = perpath + yrfolder + actdir + actpre + now.date().isoformat() + '*' + actpost
    cmd = "rsync -aXuq " +  perfile + " " + tmppath + yrfolder + actdir
    subprocess.call(cmd, shell=True)
 
class PWControl(object):
    """Main program class
    """
    def __init__(self):
        """
        ...
        """
        global port
        global tmppath
        global curpre
        global curpost
                
        self.device = Stick(port, timeout=1)
        self.staticconfig_fn = 'config/pw-conf.json'
        self.control_fn = 'config/pw-control.json'
        #self.schedule_fn = 'config/pw-schedules.json'
        
        self.last_schedule_ts = None
        self.last_control_ts = None

        self.circles = []
        self.schedules = []
        self.controls = []
        self.controlsjson = dict()
        self.save_controls = False
        
        self.bymac = dict()
        self.byname = dict()
        self.schedulebyname = dict()
        
        self.curfname = tmppath + curpre + curpost
        self.curfile = open(self.curfname, 'w')
        self.statuslogfname = tmppath+'pw-status.json'
        self.statusfile = open(self.statuslogfname, 'w')
        self.statusdumpfname = perpath+'pw-statusdump.json'
        self.actfiles = dict()
        self.logfnames = dict()
        self.daylogfnames = dict()
        self.lastlogfname = perpath+'pwlastlog.log'

        #read the static configuration
        sconf = json.load(open(self.staticconfig_fn))
        i=0
        for item in sconf['static']:
            #remove tabs which survive dialect='trimmed'
            for key in item:
                if isinstance(item[key],str): item[key] = item[key].strip()
            item['mac'] = item['mac'].upper()
            if item['production'].strip().lower() in ['true', '1', 't', 'y', 'yes', 'on']:
                item['production'] = True
            if 'revrse_pol' not in item:
                item['reverse_pol'] = False
            self.bymac[item.get('mac')]=i
            self.byname[item.get('name')]=i
            #exception handling timeouts done by circle object for init
            self.circles.append(Circle(item['mac'], self.device, item))
            self.set_interval_production(self.circles[-1])
            i += 1
            info("adding circle: %s" % (self.circles[-1].name,))
        
        #retrieve last log addresses from persistent storage
        with open(self.lastlogfname, 'a+') as f:
            f.seek(0)
            for line in f:
                parts = line.split(',')
                mac, logaddr = parts[0:2]
                if len(parts) == 4:
                    idx = int(parts[2])
                    ts = int(parts[3])
                else:
                    idx = 0
                    ts = 0
                logaddr =  int(logaddr)
                debug("mac -%s- logaddr -%s- logaddr_idx -%s- logaddr_ts -%s-" % (mac, logaddr, idx, ts))
                try:
                    self.circles[self.bymac[mac]].last_log = logaddr
                    self.circles[self.bymac[mac]].last_log_idx = idx
                    self.circles[self.bymac[mac]].last_log_ts = ts
                except:
                    error("PWControl.__init__(): lastlog mac not found in circles")
         
        self.schedulesstat = dict ((f, os.path.getmtime(f)) for f in glob.glob(schedules_path+'/*.json'))
        self.schedules = self.read_schedules()
        self.poll_configuration()

    def get_relays(self):
        """
        Update the relay state for circles with schedules enabled.
        """
        for c in self.circles:
            if c.online and c.schedule_state == 'on':
                try:
                    c.get_info()
                except (TimeoutException, SerialException, ValueError) as reason:
                    debug("Error in get_relays(): %s" % (reason,))
                    continue
                #publish relay_state for schedule-operated circles.
                #could also be done unconditionally every 15 minutes in main loop.
                self.publish_circle_state(c.mac)
                    
    def get_status_json(self, mac):
        try:
            c = self.circles[self.bymac[mac]]
            control = self.controls[self.controlsbymac[mac]]
        except:
            info("get_status_json: mac not found in circles or controls")
            return ""
        try:
            status = c.get_status()
            status["mac"] = status["mac"]
            status["monitor"] = (control['monitor'].lower() == 'yes')
            status["savelog"] = (control['savelog'].lower() == 'yes')
            #json.encoder.FLOAT_REPR = lambda f: ("%.2f" % f)
            #msg = json.dumps(status, default = jsondefault)
            msg = json.dumps(status)
        except (ValueError, TimeoutException, SerialException) as reason:
            error("Error in get_status_json: %s" % (reason,))
            msg = ""
        return str(msg)
        
    def log_status(self):
        self.statusfile.seek(0)
        self.statusfile.truncate(0)
        self.statusfile.write('{"circles": [\n')
        comma = False
        for c in self.circles:
            if comma:
                self.statusfile.write(",\n")
            else:
                comma = True
            #json.dump(c.get_status(), self.statusfile, default = jsondefault)
            self.statusfile.write(self.get_status_json(c.mac))
            #str('{"typ":"circle","ts":%d,"mac":"%s","online":"%s","switch":"%s","schedule":"%s","power":%.2f,
            #"avgpower1h":%.2f,"powts":%d,"seents":%d,"interval":%d,"production":%s,"monitor":%s,"savelog":%s}'
        self.statusfile.write('\n] }\n')
        self.statusfile.flush()
        
    def dump_status(self):
        self.statusdumpfile = open(self.statusdumpfname, 'w+')
        self.statusdumpfile.write('{"circles": [\n')
        comma = False
        for c in self.circles:
            if comma:
                self.statusdumpfile.write(",\n")
            else:
                comma = True
            json.dump(c.dump_status(), self.statusdumpfile, default = jsondefault)
        self.statusdumpfile.write('\n] }\n')
        self.statusdumpfile.close()
    
    def sync_time(self):
        for c in self.circles:
            if not c.online:
                continue
            try:
                info("sync_time: circle %s time is %s" % (c.aname, c.get_clock().isoformat()))
                if c.type()=='circle+':
                    #now = datetime.now()            
                    #local time not following DST (always non-DST)
                    locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
                    now = locnow
                    c.set_circleplus_datetime(now)
                #now = datetime.now()            
                #local time not following DST (always non-DST)
                locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
                now = locnow
                c.set_clock(now)
            except (ValueError, TimeoutException, SerialException) as reason:
                error("Error in sync_time: %s" % (reason,))

    def set_interval_production(self, c):
        if not c.online:
            return
        try:
            #TODO: Check this. Previously log_interval was only set when difference between config file and circle state
            c.set_log_interval(c.loginterval, c.production)
        except (ValueError, TimeoutException, SerialException) as reason:
            error("Error in set_interval_production: %s" % (reason,))
                            
    def generate_test_schedule(self, val):
        #generate test schedules
        if val == -2:
            testschedule = []
            for i in range (0, 336):
                testschedule.append(-1)
                testschedule.append(0)
        else:
            testschedule = []
            for i in range (0, 672):
                testschedule.append(val)
        return testschedule
        
    def read_schedules(self):
        #read schedules
        debug("read_schedules")
        newschedules = []
        self.schedulebyname = dict()
        newschedules.append(self.generate_test_schedule(-2))
        self.schedulebyname['__PW2PY__test-alternate']=0
        info("generate schedule: __PW2PY__test-alternate")
        newschedules.append(self.generate_test_schedule(10))
        self.schedulebyname['__PW2PY__test-10']=1
        info("generate schedule: __PW2PY__test-10")
        i=len(newschedules)
        
        schedule_names = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob(schedules_path+'/*.json')]
        for sched_fn in schedule_names:
            schedfpath = schedules_path+'/'+sched_fn+'.json'
            try:
                rawsched = json.load(open(schedfpath))
                self.schedulebyname[sched_fn]=i
                newschedules.append(list(itertools.chain.from_iterable(rawsched['schedule'])))
                info("import   schedule: %s.json" % (sched_fn,))
                #print("import   schedule: %s.json" % (sched_fn,))
                i += 1
            except:
                error("Unable to read or parse schedule file %s" % (schedfpath,))            
        
        return newschedules


    def apply_schedule_changes(self):
        """ in case off a failure to upload schedule,
            c.online is set to False by api, so reload handled through
            self.test_offline() and self.apply_<func>_to_circle
        """

        debug("apply_schedule_changes()")
        for c in self.circles:
            if not c.online:
                continue
            if c.schedule != None:
                if c.schedule.name in self.schedulebyname:
                    sched = self.schedules[self.schedulebyname[c.schedule.name]]
                    if sched != c.schedule._watt:
                        info("apply_schedule_changes: schedule changed. Update in circle %s - %s" % (c.name, c.schedule.name))
                        #schedule changed so upload to this circle
                        c.define_schedule(c.schedule.name, sched, time.localtime().tm_isdst)
                        try:
                            sched_state = c.schedule_state
                            c.schedule_off()
                            c.load_schedule(time.localtime().tm_isdst)
                            #update scheduleCRC
                            c.get_clock()
                            if sched_state == 'on':
                                c.schedule_on()
                        except (ValueError, TimeoutException, SerialException) as reason:
                            #failure to upload schedule.
                            c.undefine_schedule() #clear schedule forces a retry at next call
                            error("Error during uploading schedule: %s" % (reason,))
                        self.publish_circle_state(c.mac)
                else:
                    error("Error during uploading schedule. Schedule %s not found." % (c.schedule.name,))
            
    def read_apply_controls(self):
        debug("read_apply_controls")
        #read the user control settings
        controls = json.load(open(self.control_fn))  
        self.controlsjson = controls
        self.controlsbymac = dict()
        newcontrols = []        
        i=0
        for item in controls['dynamic']:
            #remove tabs which survive dialect='trimmed'
            for key in item:
                if isinstance(item[key],str): item[key] = item[key].strip()
            item['mac'] = item['mac'].upper()
            newcontrols.append(item)
            self.controlsbymac[item['mac']]=i
            i += 1
        #set log settings
        if 'log_comm' in controls:
            log_comm(str(controls['log_comm']).strip().lower() == 'yes')
            info("COMMU with str() %s" % (str(controls['log_comm']).strip().lower() == 'yes',))
            info("COMMU with u %s" % (controls['log_comm'].strip().lower() == 'yes',))
        if 'log_level' in controls:
            if str(controls['log_level']).strip().lower() == 'debug':
                log_level(logging.DEBUG)
            elif str(controls['log_level']).strip().lower() == 'info':
                log_level(logging.INFO)
            elif str(controls['log_level']).strip().lower() == 'error':
                log_level(logging.ERROR)
            else:
                log_level(logging.INFO)
        
        self.controls =  newcontrols
        for mac, idx in self.controlsbymac.items():
            self.apply_control_to_circle(self.controls[idx], mac, force=False)
           
        return
        
    def apply_control_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        updated = self.apply_schedule_to_circle(control, mac, force)
        c = self.circles[self.bymac[mac]]
        debug('circle mac: %s before1 - state [r,sw,sc] %s %s %s - scname %s' % (mac, c.relay_state, control['switch_state'], control['schedule_state'], control['schedule']))
        debug('circle mac: %s before2 - state [r,sw,sc] %s %s %s' % (c.mac, c.relay_state, c.switch_state, c.schedule_state))
        updated = updated | self.apply_schedstate_to_circle(control, mac, force)
        if control['schedule_state'] != 'on':
            updated = updated | self.apply_switch_to_circle(control, mac, force)
        else:
            #prime the switch state for consistency between circle and control
            try:
                c = self.circles[self.bymac[mac]]
                updated = updated | (c.switch_state != control['switch_state'])
                c.switch_state = control['switch_state']
            except:
                info("mac from controls not found in circles while prime switch state")
            
        if updated:
            self.publish_circle_state(mac)
        debug('circle mac: %s after1 - state [r,sw,sc] %s %s %s - scname %s' % (mac, c.relay_state, control['switch_state'], control['schedule_state'], control['schedule']))
        debug('circle mac: %s after2 - state [r,sw,sc] %s %s %s' % (c.mac, c.relay_state, c.switch_state, c.schedule_state))


    def apply_schedule_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        try:
            c = self.circles[self.bymac[mac]]                
        except:
            info("mac from controls not found in circles")
            return False
        if not c.online:
            return False

        #load new schedule if required
        schedname = str(control['schedule'])
        #make sure the scheduleCRC read from circle is set
        try:
            c.get_clock()
        except (ValueError, TimeoutException, SerialException) as reason:
            error("Error in apply_schedule_to_circle get_clock: %s" % (reason,))
            return False
        circle_changed = False
        if schedname == '':
            #no schedule specified.
            try:
                #only change schedules when schedule_state = off
                c.schedule_off()
            except (ValueError, TimeoutException, SerialException) as reason:
                error("Error in apply_schedule_to_circle schedule_off: %s" % (reason,))

            c.undefine_schedule()
            if c.scheduleCRC != 17786:
                #set always-on schedule in circle
                info('circle mac: %s needs schedule to be undefined' % (mac,))
                #print('circle mac: %s needs schedule to be undefined' % (mac,))
                try:
                    c.set_schedule_value(-1)
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_schedule_to_circle set always on schedule: %s" % (reason,))
                    return False
                circle_changed = True
        else:
            try:                
                sched = self.schedules[self.schedulebyname[schedname]]
                if c.schedule is None or schedname != c.schedule.name or sched != c.schedule._watt:
                    info('circle mac: %s needs schedule to be defined' % (mac,))
                    #print('circle mac: %s needs schedule to be defined' % (mac,))
                    #define schedule object for circle
                    c.define_schedule(schedname, sched, time.localtime().tm_isdst)
                    
                #Only upload when mismatch in CRC
                debug("apply_control_to_circle: compare CRC's: %d %d" %(c.schedule.CRC, c.scheduleCRC))
                if  c.schedule.CRC != c.scheduleCRC or c.schedule.dst != time.localtime().tm_isdst:
                    info('circle mac: %s needs schedule to be uploaded' % (mac,))
                    try:
                        c.schedule_off()
                        c.load_schedule(time.localtime().tm_isdst)
                        #update scheduleCRC
                        c.get_clock()
                    except (ValueError, TimeoutException, SerialException) as reason:
                        error("Error in apply_control_to_circle load_schedule: %s" % (reason,))
                        return False
                    circle_changed = True
            except:
                error("schedule name from controls '%s' not found in table of schedules" % (schedname,))
        return circle_changed
                                    
    def apply_switch_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        try:
            c = self.circles[self.bymac[mac]]                
        except:
            info("mac from controls not found in circles")
            return False
        if not c.online:
            return False
        switched = False
        #switch on/off if required
        sw_state = control['switch_state'].lower()
        if sw_state == 'on' or sw_state == 'off':
            sw = True if sw_state == 'on' else False
            if force or sw_state != c.relay_state or sw_state != c.switch_state:
                info('circle mac: %s needs to be switched %s' % (mac, sw_state))
                try:
                    c.switch(sw)
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle failed to switch: %s" % (reason,))
                    return False
                switched = True
        else:
            error('invalid switch_state value in controls file')
        return switched

    def apply_schedstate_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        try:
            c = self.circles[self.bymac[mac]]                
        except:
            info("mac from controls not found in circles")
            return False
        if not c.online:
            print("offline")
            return False
        switched = False
        
        #force schedule_state to off when no schedule is defined
        if ((not control['schedule']) or control['schedule'] == "") and control['schedule_state'].lower() == 'on':
            control['schedule_state'] = 'off'
            info('circle mac: %s schedule forced to off because no schedule defined' % (mac,))
            self.write_control_file()
            self.last_control_ts = os.stat(self.control_fn).st_mtime


        #switch schedule on/off if required
        sw_state = control['switch_state'].lower()
        sw = True if sw_state == 'on' else False
        sc_state = control['schedule_state'].lower()
        if sc_state == 'on' or sc_state == 'off':
            sc = True if sc_state == 'on' else False
            if force or sc_state != c.schedule_state:
                info('circle mac: %s needs schedule to be switched %s' % (mac, sc_state))
                try:
                    c.schedule_onoff(sc)
                    if not sc:
                        #make sure to put switch in proper position when switching off schedule
                        c.switch(sw)
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle failed to switch schedule: %s" % (reason,))
                    return False
                switched = True
        else:
            error('invalid schedule_state value in controls file')
        return switched
            
    def setup_actfiles(self):
        global tmppath
        global perpath
        global actpre
        global actpost
        
        #close all open act files
        for m, f in self.actfiles.items():
            f.close()
        #open actfiles according to (new) config
        self.actfiles = dict()
        #now = datetime.now()            
        #local time not following DST (always non-DST)
        locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
        now = locnow
        today = now.date().isoformat()
        yrfold = str(now.year)+'/'
        if not os.path.exists(tmppath+yrfold+actdir):
            os.makedirs(tmppath+yrfold+actdir)
        for mac, idx in self.controlsbymac.items():
            if self.controls[idx]['monitor'].lower() == 'yes':
                fname = tmppath + yrfold + actdir + actpre + today + '-' + mac + actpost
                f = open(fname, 'a')
                self.actfiles[mac]=f

    # def setup_logfiles(self):
        # global tmppath
        # global perpath
        # global logpre
        # global logpost
        
        # #name logfiles according to (new) config
        # self.logfnames = dict()
        # self.daylogfnames = dict()
        # #TODO: use locnow
        # now = datetime.now()
        # today = now.date().isoformat()
        # for mac, idx in self.controlsbymac.iteritems():
            # if self.controls[idx]['savelog'].lower() == 'yes':
                # try:
                    # if int(self.circles[self.bymac[self.controls[idx]['mac']]].loginterval) <60:
                        # #daily logfiles - persistent iso tmp
                        # #fname = tmppath + logdir + logpre + today + '-' + mac + logpost
                        # fname = perpath + yrfolder + logdir + logpre + today + '-' + mac + logpost
                        # self.daylogfnames[mac]=fname
                # except:
                    # #assume contineous logging only
                    # pass
                # #contineous log files
                # fname = perpath + yrfolder + logdir + logpre + mac + logpost
                # self.logfnames[mac]=fname
                # #f = open(fname, 'a')
                
    def rsync_to_persistent(self):
        global tmppath
        global perpath
        global actpre
        global actpost
        global logpre
        global logpost

        locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
        year = locnow.year
        if rsyncing:
            # /tmp/<year>/pwact-*
            tmpfile = tmppath + str(year) + '/' + actdir + actpre + '*' + actpost
            cmd = "rsync -aXq " +  tmpfile + " " + perpath + str(year) + '/' + actdir
            subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # /tmp/<prev_year>/pwact-*
            tmpfile = tmppath + str(year-1) + '/' + actdir + actpre + '*' + actpost
            cmd = "rsync -aXq " +  tmpfile + " " + perpath + str(year-1) + '/' + actdir
            subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        
    def cleanup_tmp(self):
        # tmpfiles = tmppath + actpre + '*' + actpost
        # for fn in glob.iglob(tmpfiles):
             # if time.time()-os.path.getmtime(fn) > cleanage:
                # os.unlink(fn)
        tmpfiles = tmppath + '*/' + actdir + actpre + '*' + actpost
        for fn in glob.iglob(tmpfiles):
             if time.time()-os.path.getmtime(fn) > cleanage:
                os.unlink(fn)
            
    def test_mtime(self, before, after):
        modified = []
        if after:
            for (bf,bmod) in list(before.items()):
                if (bf in after and after[bf] > bmod):
                    modified.append(bf)
        return modified
     
    def poll_configuration(self):
        debug("poll_configuration()")
        before = self.schedulesstat
        try:
            after = dict ((f, os.path.getmtime(f)) for f in glob.glob(schedules_path+'/*.json'))
            added = [f for f in list(after.keys()) if not f in list(before.keys())]
            removed = [f for f in list(before.keys()) if not f in list(after.keys())]
            modified = self.test_mtime(before,after)
            if (added or removed or modified):
                self.schedules = self.read_schedules()
                self.schedulesstat = after
                self.apply_schedule_changes()
                #TODO: Remove. The schedule is changed, but not the schedule_state is switched on or off!
                #for mac, idx in self.controlsbymac.iteritems():
                #    self.apply_control_to_circle(self.controls[idx], mac, force=True)
        except OSError as reason:
            error("Error in poll_configuration(): %s" % (reason,))
        
        # if self.last_schedule_ts != os.stat(self.schedule_fn).st_mtime:
            # self.last_schedule_ts = os.stat(self.schedule_fn).st_mtime
            # self.schedules = self.read_schedules() 
            # self.apply_schedule_changes()
        if self.last_control_ts != os.stat(self.control_fn).st_mtime:
            self.last_control_ts = os.stat(self.control_fn).st_mtime
            self.read_apply_controls()
            self.setup_actfiles()
            #self.setup_logfiles()            
        #failure to apply control settings to a certain circle results
        #in offline state for that circle, so it get repaired when the
        #self.test_offline() method detects it is back online
        #a failure to load a schedule data also results in online = False,
        #and recovery is done by the same functions.
        
    def process_mqtt_commands(self):
        updated = False
        while not qsub.empty():
            rcv = qsub.get()
            topic = rcv[0]
            payl = rcv[1]
            info("process_mqtt_commands: %s %s" % (topic, payl)) 
            #topic format: plugwise2py/cmd/<cmdname>/<mac>
            st = topic.split('/')
            try:
                mac = st[-1]
                cmd = st[-2]
                #msg format: json: {"mac":"...", "cmd":"", "val":""}
                msg = json.loads(payl)
                control = self.controls[self.controlsbymac[mac]]
                val = msg['val']
            except:
                error("MQTT: Invalid message format in topic or JSON payload")
                continue
            if cmd == "switch":
                val = val.lower()
                if val == "on" or val == "off":
                    control['switch_state'] = val
                    updated = self.apply_switch_to_circle(control, mac)
                    #switch command overrides schedule_state setting
                    control['schedule_state'] = "off"
                else:
                    error("MQTT command has invalid value %s" % (val,))
            elif cmd == "schedule":
                val = val.lower()
                if val == "on" or val == "off":
                    control['schedule_state'] = val
                    updated = self.apply_schedstate_to_circle(control, mac)
                else:
                    error("MQTT command has invalid value %s" % (val,))
            elif cmd == "setsched":
                error("MQTT command not implemented")
            elif cmd == "reqstate":
                #refresh power readings for circle
                try:
                    c = self.circles[self.bymac[mac]]                
                    c.get_power_usage()
                    info("Just read power for status update")
                except:
                    info("Error in reading power for status update")
                #return message is generic state message below
                
            self.publish_circle_state(mac)            
        if updated:
            self.write_control_file()
            self.last_control_ts = os.stat(self.control_fn).st_mtime
    
    def ftopic(self, keyword, mac):
        return str("plugwise2py/state/" + keyword +"/" + mac)

    def publish_circle_state(self, mac):
        qpub.put((self.ftopic("circle", mac), str(self.get_status_json(mac)), True))

    def write_control_file(self):
        #write control file for testing purposes
        fjson = open("config/pw-control.json", 'w')
        self.controlsjson['dynamic'] = self.controls
        json.dump(self.controlsjson, fjson, indent=4)
        fjson.close()
     
    def ten_seconds(self):
        """
        Failure to read an actual usage is not treated as a severe error.
        The missed values are just not logged. The circle ends up in 
        online = False, and the self.test_offline() tries to recover
        """
        self.curfile.seek(0)
        self.curfile.truncate(0)
        for mac, f in self.actfiles.items():
            try:
                c = self.circles[self.bymac[mac]]                
            except:
                error("Error in ten_seconds(): mac from controls not found in circles")
                continue  
            if not c.online:
                continue
            
            #prepare for logging values
            if epochf:
                ts = calendar.timegm(datetime.utcnow().utctimetuple())
            else:
                t = datetime.time(datetime.utcnow()-timedelta(seconds=time.timezone))
                ts = 3600*t.hour+60*t.minute+t.second
            try:
                _, usage, _, _ = c.get_power_usage()
                #print("%10d, %8.2f" % (ts, usage,))
                f.write("%5d, %8.2f\n" % (ts, usage,))
                self.curfile.write("%s, %.2f\n" % (mac, usage))
                #debug("MQTT put value in qpub")
                msg = str('{"typ":"pwpower","ts":%d,"mac":"%s","power":%.2f}' % (ts, mac, usage))
                qpub.put((self.ftopic("power", mac), msg, True))
            except ValueError:
                #print("%5d, " % (ts,))
                f.write("%5d, \n" % (ts,))
                self.curfile.write("%s, \n" % (mac,))
            except (TimeoutException, SerialException) as reason:
                #for continuous monitoring just retry
                error("Error in ten_seconds(): %s" % (reason,))
            f.flush()
            #prevent backlog in command queue
            if mqtt: self.process_mqtt_commands()
        self.curfile.flush()
        return

    # def hourly(self):
        # return
        
    def log_recording(self, control, mac):
        """
        Failure to read recordings for a circle will prevent writing any new
        history data to the log files. Also the counter in the counter file is not
        updated. Consequently, at the next call (one hour later) reading the  
        history is retried.
        """
        fileopen = False
        if control['savelog'].lower() == 'yes':
            info("%s: save log " % (mac,))
            try:
                c = self.circles[self.bymac[mac]]
            except:
                error("mac from controls not found in circles")
                return
            if not c.online:
                return
            
            #figure out what already has been logged.
            try:
                c_info = c.get_info()
                #update c.power fields for administrative purposes
                c.get_power_usage()
            except ValueError:
                return
            except (TimeoutException, SerialException) as reason:
                error("Error in log_recording() get_info: %s" % (reason,))
                return
            last = c_info['last_logaddr']
            first = c.last_log
            idx = c.last_log_idx
            if c.last_log_ts != 0:
                last_dt = datetime.utcfromtimestamp(c.last_log_ts)-timedelta(seconds=time.timezone)
            else:
                last_dt = None

            if last_dt ==None:
                debug("start with first %d, last %d, idx %d, last_dt None" % (first, last, idx))
            else:
                debug("start with first %d, last %d, idx %d, last_dt %s" % (first, last, idx, last_dt.strftime("%Y-%m-%d %H:%M")))
            #check for buffer wrap around
            #The last log_idx is 6015. 6016 is for the range function
            if last < first:
                if (first == 6015 and idx == 4) or first >= 6016:
                    first = 0
                else:
                    #last = 6016
                    #TODO: correct if needed
                    last = 6015
            log = []
            try:
                #read one more than request to determine interval of first measurement
                #TODO: fix after reading debug log
                if last_dt == None:
                    if first>0:
                        powlist = c.get_power_usage_history(first-1)
                        last_dt = powlist[3][0]
                        #The unexpected case where both consumption and production are logged
                        #Probably this case does not work at all
                        if powlist[1][0]==powlist[2][0]:
                           #not correct for out of sync usage and production buffer
                           #the returned value will be production only
                           last_dt=powlist[2][0]
                        debug("determine last_dt - buffer dts: %s %s %s %s" %
                            (powlist[0][0].strftime("%Y-%m-%d %H:%M"),
                            powlist[1][0].strftime("%Y-%m-%d %H:%M"),
                            powlist[2][0].strftime("%Y-%m-%d %H:%M"),
                            powlist[3][0].strftime("%Y-%m-%d %H:%M")))
                    elif first == 0:
                        powlist = c.get_power_usage_history(0)
                        if len(powlist) > 2 and powlist[0][0] is not None and powlist[1][0] is not None:
                            last_dt = powlist[0][0]
                            #subtract the interval between index 0 and 1
                            last_dt -= powlist[1][0] - powlist[0][0]
                        else:
                            #last_dt cannot be determined yet. wait for 2 hours of recordings. return.
                            info("log_recording: last_dt cannot be determined. circles did not record data yet.")
                            return
                       
                #loop over log addresses and write to file
                for log_idx in range(first, last+1):
                    buffer = c.get_power_usage_history(log_idx, last_dt)
                    idx = idx % 4
                    debug("len buffer: %d, production: %s" % (len(buffer), c.production))
                    for i, (dt, watt, watt_hour) in enumerate(buffer):
                        if i >= idx and not dt is None and dt >= last_dt:
                            #if the timestamp is identical to the previous, add production to usage
                            #in case of hourly production logging, and end of daylightsaving, duplicate
                            #timestamps can be present for two subsequent hours. Test the index
                            #to be odd handles this.
                            idx = i + 1
                            if dt == last_dt and c.production == True and i & 1:
                                tdt, twatt, twatt_hour = log[-1]
                                twatt+=watt
                                twatt_hour+=watt_hour
                                log[-1]=[tdt, twatt, twatt_hour]
                            else:
                                log.append([dt, watt, watt_hour])
                            info("circle buffers: %s %d %s %d %d" % (mac, log_idx, dt.strftime("%Y-%m-%d %H:%M"), watt, watt_hour))
                            debug("proce with first %d, last %d, idx %d, last_dt %s" % (first, last, idx, last_dt.strftime("%Y-%m-%d %H:%M")))
                            last_dt = dt

                # if idx < 4:
                    # #not completely read yet.
                    # last -= 1
                # if idx >= 4:
                    # #not completely read yet.
                    # last += 1
                #idx = idx % 4    
                    # #TODO: buffer is also len=4 for production?
                    # if len(buffer) == 4 or (len(buffer) == 2 and c.production == True):
                        # for i, (dt, watt, watt_hour) in enumerate(buffer):
                            # if not dt is None:
                                # #if the timestamp is identical to the previous, add production to usage
                                # #in case of hourly production logging, and end of daylightsaving, duplicate
                                # #timestamps can be present for two subsequent hours. Test the index
                                # #to be odd handles this.
                                # if dt == last_dt and c.production == True and i & 1:
                                    # tdt, twatt, twatt_hour = log[-1]
                                    # twatt+=watt
                                    # twatt_hour+=watt_hour
                                    # log[-1]=[tdt, twatt, twatt_hour]
                                # else:
                                    # log.append([dt, watt, watt_hour])
                                # debug("circle buffers: %s %d %s %d %d" % (mac, log_idx, dt.strftime("%Y-%m-%d %H:%M"), watt, watt_hour))
                            # last_dt = dt
                    # else:
                        # last -= 1
            except ValueError:
                return
                #error("Error: Failed to read power usage")
            except (TimeoutException, SerialException) as reason:
                #TODO: Decide on retry policy
                #do nothing means that it is retried after one hour (next call to this function).
                error("Error in log_recording() wile reading history buffers - %s" % (reason,))
                return
                
            debug("end   with first %d, last %d, idx %d, last_dt %s" % (first, last, idx, last_dt.strftime("%Y-%m-%d %H:%M")))

            #update last_log outside try block.
            #this results in a retry at the next call to log_recording
            c.last_log = last
            c.last_log_idx = idx
            c.last_log_ts = calendar.timegm((last_dt+timedelta(seconds=time.timezone)).utctimetuple())
            
            
            
            
            # if c.loginterval <60:
                # dayfname = self.daylogfnames[mac]                
                # f=open(dayfname,'a')
            # else:
                # f=open(fname,'a')
                
            #initialisation to a value in the past.
            #Value assumes 6016 logadresses = 6016*4 60 minutes logs = 1002.n days
            #just set this several years back. Circles may have been unplugged for a while
            fileopen = False
            f = None
            prev_dt = datetime.now()-timedelta(days=2000)
            for dt, watt, watt_hour in log:
                if not dt is None:                
                    watt = "%15.4f" % (watt,)
                    watt_hour = "%15.4f" % (watt_hour,)
                    if epochf:
                        ts_str = str(calendar.timegm((dt+timedelta(seconds=time.timezone)).utctimetuple()))
                    else:
                        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    #print("%s, %s, %s" % (ts_str, watt, watt_hour))
                    
                    #use year folder determined by timestamps in circles
                    yrfold = str(dt.year)+'/'
                    if not os.path.exists(perpath+yrfold+actdir):
                        os.makedirs(perpath+yrfold+actdir)
                    if not os.path.exists(perpath+yrfold+logdir):
                        os.makedirs(perpath+yrfold+logdir)
                    
                    if c.interval <60:
                        #log in daily file if interval < 60 minutes
                        if prev_dt.date() != dt.date():
                            #open new daily log file
                            if fileopen:
                                f.close()
                            ndate = dt.date().isoformat()
                            # persistent iso tmp
                            newfname= perpath + yrfold + logdir + logpre + ndate + '-' + mac + logpost
                            self.daylogfnames[mac]=newfname
                            f=open(newfname,'a')
                    else:
                        #log in the yearly files
                        if prev_dt.year != dt.year:
                            if fileopen:
                                f.close()                                   
                            newfname= perpath + yrfold + logdir + logpre + mac + logpost
                            self.logfnames[mac]=newfname
                            f=open(newfname,'a')
                    fileopen = True
                    prev_dt = dt                
                    f.write("%s, %s, %s\n" % (ts_str, watt, watt_hour))
                    #debug("MQTT put value in qpub")
                    msg = str('{"typ":"pwenergy","ts":%s,"mac":"%s","power":%s,"energy":%s,"interval":%d}' % (ts_str, mac, watt.strip(), watt_hour.strip(),c.interval))
                    qpub.put((self.ftopic("energy", mac), msg, True))
            if not f == None:
                f.close()
                
            if fileopen:
                info("circle buffers: %s %s read from %d to %d" % (mac, c.name, first, last))
                
            #store lastlog addresses to file
            with open(self.lastlogfname, 'w') as f:
                for c in self.circles:
                    f.write("%s, %d, %d, %d\n" % (c.mac, c.last_log, c.last_log_idx, c.last_log_ts))
                            
        return fileopen #if fileopen actual writing to log files took place
        
    # def log_recordings(self):
        # debug("log_recordings")
        # for mac, idx in self.controlsbymac.iteritems():
            # self.log_recording(self.controls[idx], mac)

    def test_offline(self):
        """
        When an unrecoverable communication failure with a circle occurs, the circle
        is set online = False. This function will test on this condition and if offline,
        it test whether it is available again, and if so, it will recover
        control settings and switching schedule if needed.
        In case the circle was offline during initialization, a reinit is performed.
        """
        for c in self.circles:
            if not c.online:
                try:
                    c.ping()
                    if c.online:
                        #back online. Make sure switch and schedule is ok
                        if not c.initialized:
                            c.reinit()
                            self.set_interval_production(c)
                        idx=self.controlsbymac[c.mac]
                        self.apply_control_to_circle(self.controls[idx], c.mac)
                except ValueError:
                    continue
                except (TimeoutException, SerialException) as reason:
                    debug("Error in test_offline(): %s" % (reason,))
                    continue
                                
    def reset_all(self):
        #NOTE: Untested function, for example purposes
        print("Untested function, for example purposes")
        print("Aborting. Remove next line to continue")
        krak
        #
        #TODO: Exception handling
        for c in self.circles:
            if c.name != 'circle+':
                print('resetting '+c.name)
                c.reset()
        for c in self.circles:
            if c.name == 'circle+':
                print('resetting '+c.name)
                c.reset()
        print('resetting stick')
        self.device.reset()
        print('sleeping 60 seconds to allow devices to be reset themselves')
        time.sleep(60)

    def init_network(self):
        #NOTE: Untested function, for example purposes
        print("Untested function, for example purposes")
        print("Aborting. Remove next line to continue")
        krak
        #TODO: Exception handling        
        #
        #connect stick and circle+ (=network controller)
        #
        #First query status. An exception is expected due to an short 0011 response.
        #000A/0011
        try:
            self.device.status()
        except:
            pass
        success = False
        for i in range(0,10):
            print("Trying to connect to circleplus ...")
            #try to locate a circleplus on the network    
            #0001/0002/0003 request/responses
            try:
                success = self.device.find_circleplus()
            except:
                #Not sure whether something should be handled
                pass
            #try to connect to circleplus on the network
            #0004/0005
            if success:
                try:
                    self.device.connect_circleplus()
                except:
                    pass
                #now unsolicited 0061 FFFD messages may arrive from circleplus
                #
                #now check for proper (long) status reply
                #000A/0011
                try:
                    self.device.status()
                    #stop the retry loop in case of success
                    break
                except:
                    success = False
            print("sleep 30 seconds for next retry ...")
            time.sleep(30)

    def connect_node_by_mac(self, newnodemac):
        #TODO: Exception handling
        #
        #the circleplus maintains a table of known nodes
        #nodes can be added to this table without ever having been on the network.
        #     s.join_node('mac', True), where s is the Stick object
        #nodes can also be removed from the table with methods:
        #     cp.remove_node('mac'), where cp is the circleplus object.
        #for demonstrative purposes read and print the table
        print(self.circles[0].read_node_table())
      
        #Inform network that nodes are allowed to join the network
        #Nodes may start advertising themselves with a 0006 message.
        self.device.enable_joining(True)   
        time.sleep(5)
        #0006 may be received
        #Now add the given mac id to the circleplus node table
        self.device.join_node(newnodemac, True)            
        #now unsolicited 0061 FFFD messages may arrive from node if it was in a resetted state
        #
        #sleep to allow a resetted node to become operational
        time.sleep(60)
        #
        #test the node, assuming it is already in the configuration files
        try:
            print(self.circles[self.bymac[newnodemac]].get_info())
        except:
            print('new node not detected ...')        
        #
        #end the joining process
        self.device.enable_joining(False)
        #
        #Finally read and print the table of nodes again
        print(self.circles[0].read_node_table())

        
    def connect_unknown_nodes(self):
        for newnodemac in self.device.unjoined:
            newnode = None
            try:
                newnode = self.circles[self.bymac[newnodemac]]
            except:
                info("connect_unknown_node: not joining node with MAC %s: not in configuration" % (newnodemac,))        
            #accept or reject join based on occurence in pw-conf.json
            self.device.join_node(newnodemac, newnode != None)
        #clear the list
        self.device.unjoined.clear()
        #a later call to self.test_offline will initialize the new circle(s)
        #self.test_offline()

        
    def run(self):
        global mqtt
        
        locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
        now = locnow
        day = now.day
        hour = now.hour
        minute = now.minute
        dst = time.localtime().tm_isdst

        self.sync_time()
        self.dump_status()
        #self.log_recordings()
        
        # #SAMPLE: demonstration of connecting 'unknown' nodes
        # #First a known node gets removed and reset, and than
        # #it is added again by the connect_node_by_mac() method.
        # cp=self.circles[0]
        # c=self.circles[6]
        # try:
            # c.reset()
        # except:
            # pass
        # cp.remove_node(c.mac)
        # time.sleep(60)
        # cp.remove_node(c.mac)
        # time.sleep(2)
        # try:
            # print c.get_info()
        # except:
            # pass
        # self.connect_node_by_mac(c.mac)
        # try:
            # print c.get_info()
        # except:
            # pass
            
        circleplus = None
        for c in self.circles:
            try:
                if c.get_info()['type'] == 'circle+':
                    circleplus = c
            except:
                pass
        if circleplus != None:
            debug("joined node table: %s" % (circleplus.read_node_table(),))
      
        #Inform network that nodes are allowed to join the network
        #Nodes may start advertising themselves with a 0006 message.
        self.device.enable_joining(True)   

        logrecs = True
        while 1:
            #check whether user defined configuration has been changed
            #when schedules are changed, this call can take over ten seconds!
            self.test_offline()
            self.poll_configuration()
            ##align with the next ten seconds.
            #time.sleep(10-datetime.now().second%10)
            #align to next 10 second boundary, while checking for input commands.
            ref = datetime.now()
            proceed_at = ref + timedelta(seconds=(10 - ref.second%10), microseconds= -ref.microsecond)
            while datetime.now() < proceed_at:
                if mqtt: self.process_mqtt_commands()
                time.sleep(0.5)
            #prepare for logging values
            prev_dst = dst
            prev_day = day
            prev_hour = hour
            prev_minute = minute
            
            #now = datetime.now()            
            #local time not following DST (always non-DST)
            locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
            now = locnow
            
            dst = time.localtime().tm_isdst
            day = now.day
            hour = now.hour
            minute = now.minute
            
            #read historic data only one circle per minute
            if minute != prev_minute:
                logrecs = True
            
            #get relays state just after each new quarter hour for circles operating a schedule.
            if minute % 15 == 0 and now.second > 8:
                self.get_relays()
                
            #add configured unjoined nodes every minute.
            #although call is issued every hour
            if minute != prev_minute:
                self.connect_unknown_nodes()

            if day != prev_day:
                self.setup_actfiles()
            self.ten_seconds()
            self.log_status()
            if hour != prev_hour:
                #self.hourly()
                logrecs = True
                #self.log_recordings()
                self.rsync_to_persistent()
                if hour == 4:
                    self.sync_time()
                    info("Daily 4 AM: time synced circles.")
                #Allow resetted or unknown nodes to join the network every hour
                #NOTE: Not fully tested.
                try:
                    self.device.enable_joining(True)
                except:
                    error("PWControl.run(): Communication error in enable_joining")
                self.dump_status()
            if day != prev_day:
                #self.daily()
                self.cleanup_tmp()
                
            #Hourly log_recordings. Process one every ten seconds
            if logrecs:
                breaked = False
                for c in self.circles:
                    idx=self.controlsbymac[c.mac]
                    if self.log_recording(self.controls[idx], c.mac):
                        #actual recordings written to logfile
                        #allow next circle to be logged in next ten seconds.
                        breaked = True
                        break
                if not breaked:
                    #all circles have been processed
                    logrecs = False
            
            #update schedules after change in DST. Update one every ten seconds
            for c in self.circles:
                if c.online and c.schedule != None and c.schedule.dst != time.localtime().tm_isdst:
                    info("Circle '%s' schedule shift due to DST changed." % (c.name,))
                    idx=self.controlsbymac[c.mac]
                    self.apply_control_to_circle(self.controls[idx], c.mac, force=True)
                    break

                
            #test    
            # self.log_recordings()
            # self.rsync_to_persistent()
            # self.setup_actfiles()
            # self.cleanup_tmp()

init_logger(logpath+"pw-logger.log", "pw-logger")
log_level(logging.DEBUG)
log_comm(True)

try:
    qpub = queue.Queue()
    qsub = queue.Queue()
    mqtt_t = None
    if  not mqtt:
        error("No MQTT python binding installed (mosquitto-python)")
    elif 'mqtt_ip' in cfg and 'mqtt_port' in cfg:
        #connect to server and start worker thread.
        if 'mqtt_user' in cfg and 'mqtt_password' in cfg:
            mqttclient = Mqtt_client(cfg['mqtt_ip'], cfg['mqtt_port'], qpub, qsub,"Plugwise-2-py",cfg['mqtt_user'],cfg['mqtt_password'])
        else:
            mqttclient = Mqtt_client(cfg['mqtt_ip'], cfg['mqtt_port'], qpub, qsub, "Plugwise-2-py")
        mqttclient.subscribe("plugwise2py/cmd/#")
        mqtt_t = threading.Thread(target=mqttclient.run)
        mqtt_t.setDaemon(True)
        mqtt_t.start()
        info("MQTT thread started")
    else:
        error("No MQTT broker and port configured")
        mqtt = False

    main=PWControl()
    main.run()
except:
    close_logcomm()
    raise
