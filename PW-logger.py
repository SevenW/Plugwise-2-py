#!/usr/bin/env python

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
import plugwise.util
from datetime import datetime, timedelta
import time
import calendar
import subprocess
import glob
import os
import logging

import pprint as pp
import json

def jsondefault(o):
    return o.__dict__

#plugwise.util.DEBUG_PROTOCOL = False
plugwise.util.LOG_COMMUNICATION = False
#plugwise.util.LOG_LEVEL = 2

cfg = json.load(open("pw-hostconfig.json"))
tmppath = cfg['tmp_path']+'/'
perpath = cfg['permanent_path']+'/'
logpath = cfg['log_path']+'/'
port = cfg['serial']
epochf = False
if cfg.has_key('log_format') and cfg['log_format'] == 'epoch':
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
        self.staticconfig_fn = 'pw-conf.json'
        self.control_fn = 'pw-control.json'
        self.schedule_fn = 'pw-schedules.json'
        
        self.last_schedule_ts = None
        self.last_control_ts = None

        self.circles = []
        self.schedules = []
        self.controls = []
        
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
            self.bymac[item.get('mac')]=i
            self.byname[item.get('name')]=i
            #exception handling timeouts done by circle object for init
            self.circles.append(Circle(item['mac'], self.device, item))
            self.set_interval_production(self.circles[-1])
            i += 1
            info("adding circle: %s" % (self.circles[-1].attr['name'],))
        
        #retrieve last log addresses from persistent storage
        with open(self.lastlogfname, 'r+') as f:
            for line in f:
                mac, logaddr = line.split(',')
                logaddr =  int(logaddr)
                #print ("mac -%s- logaddr -%s-" % (mac, logaddr))
                try:
                    self.circles[self.bymac[mac]].last_log = logaddr
                except:
                    error("PWControl.__init__(): lastlog mac not found in circles")
         
        self.poll_configuration()

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
            json.dump(c.get_status(), self.statusfile, default = jsondefault)
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
                info("sync_time: circle %s time is %s" % (c.attr['name'], c.get_clock().isoformat()))
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
            prod = c.attr['production'].strip().lower() in ['true', '1', 't', 'y', 'yes', 'on']
            interv = int(c.attr['loginterval'].strip())
            if (c.interval != interv) or (c.production != prod):
                c.set_log_interval(interv, prod)
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
        importedschedules = []
        newschedules = []
        self.schedulebyname = dict()
        newschedules.append(self.generate_test_schedule(-2))
        self.schedulebyname['test-alternate']=0
        newschedules.append(self.generate_test_schedule(10))
        self.schedulebyname['test-10']=1
        i=len(newschedules)
        
        schedules = json.load(open(self.schedule_fn))        
        for item in schedules['schedules']:        
            #remove tabs which survive dialect='schedule'
            for key in item:
                if isinstance(item[key],str): item[key] = item[key].strip()
            self.schedulebyname[item.get('Name')]=i
            importedschedules.append(item)
            i += 1

        for schedule in importedschedules:
            sched = ()
            for i in range(0, 7):
                sched += eval(schedule['Day_%d' % i].replace(';',','))
            newschedules.append(sched)
            #print sched
            #print len(sched)
        return newschedules

    def apply_schedule_changes(self):
        """ in case off a failure to upload schedule,
            c.online is set to False by api, so reload handled through
            self.test_offline() and self.apply_control_to_circle
        """

        debug("apply_schedule_changes")
        for c in self.circles:
            if not c.online:
                continue
            if c.schedule != None:
                if c.schedule.name in self.schedulebyname:
                    sched = self.schedules[self.schedulebyname[c.schedule.name]]
                    if sched != c.schedule._watt:
                        info("apply_schedule_changes: schedule changed. Update in circle")
                        #schedule changed so upload to this circle
                        c.define_schedule(c.schedule.name, sched, time.daylight)
                        try:
                            c.load_schedule(time.daylight)
                            #update scheduleCRC
                            c.get_clock()
                        except (ValueError, TimeoutException, SerialException) as reason:
                            #failure to upload schedule.
                            c.undefine_schedule() #clear schedule forces a retry at next call
                            error("Error during uploading schedule: %s" % (reason,))
            
    def read_control(self):
        debug("read_control")
        #read the user control settings
        controls = json.load(open(self.control_fn))        
        self.controlsbymac = dict()
        newcontrols = []        
        i=0
        for item in controls['dynamic']:
            #remove tabs which survive dialect='trimmed'
            for key in item:
                if isinstance(item[key],str): item[key] = item[key].strip()
            newcontrols.append(item)
            self.controlsbymac[item['mac']]=i
            i += 1
        #set log settings
        if controls.has_key('log_comm'):
            plugwise.util.LOG_COMMUNICATION = controls['log_comm'].strip().lower() == 'yes'
        if controls.has_key('log_level'):
            if controls['log_level'].strip().lower() == 'debug':
                log_level(logging.DEBUG)
            elif controls['log_level'].strip().lower() == 'info':
                log_level(logging.INFO)
            elif controls['log_level'].strip().lower() == 'error':
                log_level(logging.ERROR)
            else:
                log_level(logging.INFO)
        
        return newcontrols
        
    def apply_control_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        try:
            c = self.circles[self.bymac[mac]]                
        except:
            info("mac from controls not found in circles")
            return
        if not c.online:
            return False

        #load new schedule if required
        schedname = control['schedule']
        #make sure the scheduleCRC read from circle is set
        try:
            c.get_clock()
        except (ValueError, TimeoutException, SerialException) as reason:
            error("Error in apply_control_to_circle get_clock: %s" % (reason,))
            return False
        if schedname == '':
            #no schedule specified.
            c.schedule = None
            if c.scheduleCRC != 17786:
                #set always-on schedule in circle
                info('circle mac: %s needs schedule to be undefined' % (mac,))
                try:
                    c.set_schedule_value(-1) 
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle set always on schedule: %s" % (reason,))
                    return False
        else:
            try:                
                sched = self.schedules[self.schedulebyname[schedname]]
                if c.schedule is None or schedname != c.schedule.name:
                    info('circle mac: %s needs schedule to be defined' % (mac,))
                    #define schedule object for circle
                    c.define_schedule(schedname, sched, time.daylight)
                #Only upload when mismatch in CRC
                debug("apply_control_to_circle: compare CRC's: %d %d" %(c.schedule.CRC, c.scheduleCRC))
                if  c.schedule.CRC != c.scheduleCRC or c.schedule.dst != time.daylight:
                    info('circle mac: %s needs schedule to be uploaded' % (mac,))
                    try:
                        c.schedule_off()
                        c.load_schedule(time.daylight)
                        #update scheduleCRC
                        c.get_clock()
                        #at least for dst_toggle
                        force = True
                    except (ValueError, TimeoutException, SerialException) as reason:
                        error("Error in apply_control_to_circle load_schedule: %s" % (reason,))
                        return False
            except:
                error("schedule name from controls not found in table of schedules")
                                    
        #switch on/off if required
        sw_state = control['switch_state'].lower()
        if sw_state == 'on' or sw_state == 'off':
            sw = True if sw_state == 'on' else False
            if force or sw_state != c.relay_state:
                info('circle mac: %s needs to be switched %s' % (mac, sw_state))
                try:
                    c.switch(sw)
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle failed to switch: %s" % (reason,))
                    return False
        else:
            error('invalid switch_state value in controls file')

        #switch schedule on/off if required
        sc_state = control['schedule_state'].lower()
        if sc_state == 'on' or sc_state == 'off':
            sc = True if sc_state == 'on' else False
            if force or sc_state != c.schedule_state:
                info('circle mac: %s needs schedule to be switched %s' % (mac, sc_state))
                try:
                    c.schedule_onoff(sc)
                    if not sc:
                        #make sure to put switch in proper position when switcihng off schedule
                        c.switch(sw)
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle failed to switch schedule: %s" % (reason,))
                    return False
        else:
            error('invalid schedule_state value in controls file')
        return True

    def apply_control_changes(self, force=False):
        debug("apply_control_changes")
        for mac, idx in self.controlsbymac.iteritems():
            self.apply_control_to_circle(self.controls[idx], mac, force)
            
    def setup_actfiles(self):
        global tmppath
        global perpath
        global actpre
        global actpost
        
        #close all open act files
        for m, f in self.actfiles.iteritems():
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
        for mac, idx in self.controlsbymac.iteritems():
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
                    # if int(self.circles[self.bymac[self.controls[idx]['mac']]].attr['loginterval']) <60:
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
        
    def poll_configuration(self):
        debug("poll_configuration()")
        if self.last_schedule_ts != os.stat(self.schedule_fn).st_mtime:
            self.last_schedule_ts = os.stat(self.schedule_fn).st_mtime
            self.schedules = self.read_schedules() 
            self.apply_schedule_changes()
        if self.last_control_ts != os.stat(self.control_fn).st_mtime:
            self.last_control_ts = os.stat(self.control_fn).st_mtime
            self.controls = self.read_control()
            self.apply_control_changes()
            self.setup_actfiles()
            #self.setup_logfiles()            
        #failure to apply control settings to a certain circle results
        #in offline state for that circle, so it get repaired when the
        #self.test_offline() method detects it is back online
        #a failure to load a schedule data also results in online = False,
        #and recovery is done by the same functions.
     
    def ten_seconds(self):
        """
        Failure to read an actual usage is not treated as a severe error.
        The missed values are just not logged. The circle ends up in 
        online = False, and the self.test_offline() tries to recover
        """
        self.curfile.seek(0)
        self.curfile.truncate(0)
        for mac, f in self.actfiles.iteritems():
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
            except ValueError:
                #print("%5d, " % (ts,))
                f.write("%5d, \n" % (ts,))
                self.curfile.write("%s, \n" % (mac,))
            except (TimeoutException, SerialException) as reason:
                #for contineous monitoring just retry
                error("Error in ten_seconds(): %s" % (reason,))
            f.flush()
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
            #print("[%s: log to %s]" % (mac, fname))
            try:
                c = self.circles[self.bymac[mac]]
            except:
                info("mac from controls not found in circles")
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
            #check for buffer wrap around
            #The last log_idx is 6015. 6016 is for the range function
            if last < first:
                if first >= 6016:
                    first = 0
                else:
                    last = 6016
            last_dt = None
            log = []
            try:
                #read one more than request to determine interval of first measurement
                if first>0:
                    powlist = c.get_power_usage_history(first-1)
                    last_dt = powlist[3][0]
                    if powlist[1][0]==powlist[2][0]:
                       #not correct for out of sync usage and production buffer
                       #the returned value will be production only
                       last_dt=powlist[2][0]
                       
                #loop over log addresses and write to file
                for log_idx in range(first, last):
                    buffer = c.get_power_usage_history(log_idx, last_dt)
                    if len(buffer) == 4 or (len(buffer) == 2 and c.production == True):
                        for i, (dt, watt, watt_hour) in enumerate(buffer):
                            if not dt is None:
                                #if the timestamp is identical to the previous, add production to usage
                                #in case of hourly production logging, and end of daylightsaving, duplicate
                                #timestamps can be present for two subsequent hours. Test the index
                                #to be odd handles this.
                                if dt == last_dt and c.production == True and i & 1:
                                    tdt, twatt, twatt_hour = log[-1]
                                    twatt+=watt
                                    twatt_hour+=watt_hour
                                    log[-1]=[tdt, twatt, twatt_hour]
                                else:
                                    log.append([dt, watt, watt_hour])
                                debug("circle buffers: %s %d %s %d %d" % (mac, log_idx, dt.strftime("%Y-%m-%d %H:%M"), watt, watt_hour))
                            last_dt = dt
                    else:
                        last -= 1
            except ValueError:
                return
                #error("Error: Failed to read power usage")
            except (TimeoutException, SerialException) as reason:
                #TODO: Decide on retry policy
                #do nothing means that it is retried after one hour (next call to this function).
                error("Error in log_recording() wile reading history buffers - %s" % (reason,))
                return
            
            #update last_log outside try block.
            #this results in a retry at the next call to log_recording
            c.last_log = last
            
            # if c.attr['loginterval'] <60:
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
            if not f == None:
                f.close()
                
            if fileopen:
                info("circle buffers: %s %s read from %d to %d" % (mac, c.attr['name'], first, last))
                
            #store lastlog addresses to file
            with open(self.lastlogfname, 'w') as f:
                for c in self.circles:
                    f.write("%s, %d\n" % (c.mac, c.last_log))
                            
        return fileopen #if fileopen actual writing to log files took place
        
    def log_recordings(self):
        debug("log_recordings")
        for mac, idx in self.controlsbymac.iteritems():
            self.log_recording(self.controls[idx], mac)

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
        print "Untested function, for example purposes"
        print "Aborting. Remove next line to continue"
        krak
        #
        #TODO: Exception handling
        for c in self.circles:
            if c.attr['name'] != 'circle+':
                print 'resetting '+c.attr['name']
                c.reset()
        for c in self.circles:
            if c.attr['name'] == 'circle+':
                print 'resetting '+c.attr['name']
                c.reset()
        print 'resetting stick'
        self.device.reset()
        print 'sleeping 60 seconds to allow devices to be reset themselves'
        time.sleep(60)

    def init_network(self):
        #NOTE: Untested function, for example purposes
        print "Untested function, for example purposes"
        print "Aborting. Remove next line to continue"
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
            print "Trying to connect to circleplus ..."
            #try to locate a circleplus on the network    
            #0001/0002/0003 request/responses
            try:
                success,cpmac = self.device.find_circleplus()
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
            print "sleep 30 seconds for next retry ..."
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
        print self.circles[0].read_node_table()
      
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
            print self.circles[self.bymac[newnodemac]].get_info()
        except:
            print 'new node not detected ...'        
        #
        #end the joining process
        self.device.enable_joining(False)
        #
        #Finally read and print the table of nodes again
        print self.circles[0].read_node_table()

        
    def connect_unknown_node(self, newnodemac):
        #NOTE: Not implemented
        print "Not implemented"
        print "Aborting. Remove next line to continue"
        krak
        #Basically the flow is the same as in self.connect_node_by_mac(),
        #except that now the mac-id of the new node needs to be extracted from
        #the 0006 messages from the node.
        #handling of this is not yet in the api module.
        #a listen method should be added for 0006 messages, which may just result
        #in a timeout when not received.
        
        
    def run(self):
        locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
        now = locnow
        day = now.day
        hour = now.hour
        minute = now.minute
        dst = time.daylight

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
            
        logrecs = True
        while 1:
            #check whether user defined configuration has been changed
            #when schedules are changed, this call can take over ten seconds!
            self.test_offline()
            self.poll_configuration()
            #align with the next ten seconds.
            time.sleep(10-datetime.now().second%10)
            #prepare for logging values
            prev_dst = dst
            prev_day = day
            prev_hour = hour
            prev_minute = minute
            
            #now = datetime.now()            
            #local time not following DST (always non-DST)
            locnow = datetime.utcnow()-timedelta(seconds=time.timezone)
            now = locnow
            
            dst = time.daylight
            day = now.day
            hour = now.hour
            minute = now.minute
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
                if c.online and c.schedule != None and c.schedule.dst != time.daylight:
                    info("Circle '%s' schedule shift due to DST changed." % (self.attr['name'],))
                    idx=self.controlsbymac[c.mac]
                    self.apply_control_to_circle(self.controls[idx], c.mac)
                    break

                
            #test    
            # self.log_recordings()
            # self.rsync_to_persistent()
            # self.setup_actfiles()
            # self.cleanup_tmp()

init_logger(logpath+"pw-logger.log", "pw-logger")
log_level(logging.INFO)
main=PWControl()
main.run()
close_logcomm()
