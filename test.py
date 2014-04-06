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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Plugwise-2-py.  If not, see <http://www.gnu.org/licenses/>. 
#

from serial.serialutil import SerialException

from plugwise import *
import plugwise.util
from datetime import datetime, timedelta
import subprocess
import glob
import os

import pprint as pp
import csv
import json

plugwise.util.DEBUG_PROTOCOL = False
plugwise.util.LOG_COMMUNICATION = False
plugwise.util.LOG_LEVEL = 2

cfg = json.load(open("pw-hostconfig.json"))
tmppath = cfg['tmp_path']
perpath = cfg['permanent_path']
port = cfg['serial']
rsyncing = True
print type(tmppath)
print cfg
if tmppath == None or tmppath == "":
    tmppath = perpath
    rsyncing = False
print(rsyncing)
print(perpath)
print(tmppath)
csv.register_dialect('trimmed', skipinitialspace=True)
csv.register_dialect('schedule', delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL, skipinitialspace=True)

now = datetime.now()
day = now.day
hour = now.hour
minute = now.minute

class DummyStick(SerialComChannel):
    """simulates Plugwise Stick"""

    def __init__(self, port=0, timeout=DEFAULT_TIMEOUT):
        #SerialComChannel.__init__(self, port=port, timeout=timeout)
        #self.init()
        return

    def init(self):
        #"""send init message to the stick"""
        #msg = PlugwiseStatusRequest().serialize()
        #self.send_msg(msg)
        #resp = self.expect_response(PlugwiseStatusResponse)
        #debug(str(resp))
        return

    def send_msg(self, cmd):
        #log communication done in serialize function of message object. Could be too early!
        debug("SEND %4d %s" % (len(cmd), repr(cmd)))
        #self.write(cmd)
        #resp = self.expect_response(PlugwiseAckResponse)
        #success = False
        #if resp.status.value == 0xC1:
        #    success = True
        #return (success, resp.command_counter)
        return (False, 0)

    def _recv_response(self, retry_timeout=5):
        await_response = True
        msg = ""
        retry_timeout += 1
        while await_response:
            msg += self.readline()
            # if msg == b"":
                # logcomm("TOUT      '' - <!> Timeout on serial port" )        
                # raise TimeoutException("Timeout while waiting for response from device")                
            # #debug("read:"+repr(msg)+" with length "+str(len(msg)))
            
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
            if (msg == b"") or (msg[-1] != '\n'):
                retry_timeout -= 1
                if retry_timeout <= 0:
                    if (msg != b""):
                        logcomm("TOUT %4d %s - <!> Timeout on serial port" % ( len(msg), repr(msg)))  
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
                logcomm("DSTR %4d %s" % ( len(msg[:header_start]), repr(msg[:header_start])))
                msg = msg[header_start:]
                
            if msg.find('#') >= 0:
                logcomm("DTRC %4d %s" % ( len(msg), repr(msg)))
                msg = ""
            elif len(msg)<22:
                # Ignore. It is too short to interpet as a message.
                # It may be part of Stick debug messages.
                logcomm("DSHR %4d %s" % ( len(msg), repr(msg)))
                msg = ""
            else:
                #message can be interpreted as response
                #perform logcomm after interpetation of response
                #logcomm("RECV %4d %s" % ( len(msg), repr(msg)))
                await_response = False
        return msg
        
    def is_in_sequence(self, resp, seqnr):
        if not seqnr is None and resp.command_counter != seqnr:
            error("Out of sequence message. Expected seqnr %s, received seqnr %s" % (seqnr, resp.command_counter))
            return False
        else:
            return True

    def expect_response(self, response_class, src_mac=None, seqnr=None, retry_timeout=5):
        #error("encountered protocol error:"+"DummyStick")
        resp = response_class(seqnr)
        return resp

    def enable_joining(self, enabled):
        req = PlugwiseEnableJoiningRequest('', enabled)
        _, seqnr  = self.send_msg(req.serialize())
        self.expect_response(PlugwiseAckMacResponse)

    def join_node(self, newmac, permission):
        req = PlugwiseJoinNodeRequest(newmac, permission)
        _, seqnr  = self.send_msg(req.serialize())
        #No response other then normal ack
        #After this an unsollicted 0061 response from the circle may be received.

    def reset(self):
        type = 0
        req = PlugwiseResetRequest(self.mac, type, 20)
        _, seqnr  = self.send_msg(req.serialize())
        resp = self.expect_response(PlugwiseAckMacResponse)
        return resp.status.value

    def status(self):
        req = PlugwiseStatusRequest(self.mac)
        _, seqnr  = self.send_msg(req.serialize())
        #TODO: There is a short and a long response to 0011.
        #The short reponse occurs when no cirlceplus is connected, and has two byte parameters.
        #The short repsonse is likely not properly handled (exception?)
        resp = self.expect_response(PlugwiseStatusResponse)
        return        
        
    def find_circleplus(self):
        req = PlugwiseQueryCirclePlusRequest(self.mac)
        _, seqnr  = self.send_msg(req.serialize())
        #Receive the circle+ response, but possibly, only an end-protocol response is seen.
        success = False
        circleplusmac = None
        try:
            resp = self.expect_response(PlugwiseQueryCirclePlusResponse)
            success=True
            circleplusmac = resp.new_node_mac_id.value
        except (TimeoutException, SerialException) as reason:
            error("Error: %s, %s" % (datetime.now().isoformat(), reason,))        
        return success,circleplusmac

    def connect_circleplus(self):
        req = PlugwiseConnectCirclePlusRequest(self.mac)
        _, seqnr  = self.send_msg(req.serialize())
        resp = self.expect_response(PlugwiseConnectCirclePlusResponse)
        return resp.existing.value, self.allowed.value        


class PWControl(object):
    """Main program class
    """
    def __init__(self):
        """
        ...
        """
        global port
        global tmppath

        self.statuslogfname = tmppath+'/pwstatuslog.log'
        self.statusfile = open(self.statuslogfname, 'w')
        
        try:
            self.device = Stick(port, timeout=1)
        except:
            self.device = DummyStick(port, timeout=1)
            print("DummyStick")
        self.staticconfig_fn = 'plugwise.cfg'
        self.control_fn = 'plugwise_control.csv'
        self.schedule_fn = 'schedule.csv'
        
        self.last_schedule_ts = None
        self.last_control_ts = None

        self.circles = []
        self.schedules = []
        self.controls = []
        
        self.bymac = dict()
        self.byname = dict()
        self.schedulebyname = dict()
        

        #read the static configuration
        f = open(self.staticconfig_fn)
        dr = csv.DictReader(f, restkey="therest", restval=0, dialect='trimmed')
        self.fieldnames = dr.fieldnames

        i=0
        for row in dr:
            self.bymac[row.get('mac')]=i
            self.byname[row.get('name')]=i
            #exception handling timeouts done by circle object for init
            self.circles.append(Circle(row['mac'], self.device, row))
            self.set_interval_production(self.circles[-1])
            i += 1
            print self.circles[-1].attr['name']
        #print self.fieldnames
        #print self.bymac
                  
        self.poll_configuration()

    def log_status(self):
        for c in self.circles:
            self.statusfile.write(c.attr['name'] + '\n')
            self.statusfile.write(pp.pformat(c.get_status(), depth=2))
            self.statusfile.write("\n\n")

    def sync_time(self):
        for c in self.circles:
            if not c.online:
                continue
            try:
                if c.type()=='circle+':
                    now=datetime.now()
                    c.set_circleplus_datetime(now)
                now=datetime.now()
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
        f = open(self.schedule_fn)
        dr = csv.DictReader(f, restkey="therest", restval=0, dialect='schedule')
        Schedulefieldnames = dr.fieldnames
        importedschedules = []
        newschedules = []
        self.schedulebyname = dict()
        newschedules.append(self.generate_test_schedule(-2))
        self.schedulebyname['test-alternate']=0
        newschedules.append(self.generate_test_schedule(10))
        self.schedulebyname['test-10']=1
        i=len(newschedules)
        for row in dr:
            self.schedulebyname[row.get('Name')]=i
            importedschedules.append(row)
            i += 1
        f.close()

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
                        print "apply_schedule_changes: schedule changed. Update in circle"
                        #schedule changed so upload to this circle
                        c.define_schedule(c.schedule.name, sched)
                        try:
                            c.load_schedule()
                            #update scheduleCRC
                            c.get_clock()
                        except (ValueError, TimeoutException, SerialException) as reason:
                            #failure to upload schedule.
                            c.undefine_schedule() #clear schedule forces a retry at next call
                            error("Error during uploading schedule: %s" % (reason,))
            
    def read_control(self):
        debug("read_control")
        #read the user control settings
        f = open(self.control_fn)
        dr = csv.DictReader(f, restkey="therest", restval=0, dialect='trimmed')
        fieldnames = dr.fieldnames
        self.controlsbymac = dict()
        i=0
        newcontrols = []
        for row in dr:
            newcontrols.append(row)
            self.controlsbymac[row['mac']]=i
            i += 1
        f.close()
        return newcontrols
            
    def apply_control_to_circle(self, control, mac, force=False):
        """apply control settings to circle
        in case of a communication problem, c.online is set to False by api
        self.test_offline() will apply the control settings again by calling this function
        """
        try:
            c = self.circles[self.bymac[mac]]                
        except:
            print "mac from controls not found in circles"
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
                try:
                    c.set_schedule_value(-1) 
                except (ValueError, TimeoutException, SerialException) as reason:
                    error("Error in apply_control_to_circle set always on schedule: %s" % (reason,))
                    return False
        else:
            try:                
                sched = self.schedules[self.schedulebyname[schedname]]
                if c.schedule is None or schedname != c.schedule.name:
                    #define schedule object for circle
                    c.define_schedule(schedname, sched)
                    #TODO: Not fail safe: Only upload when mismatch in CRC
                    if  c.schedule.CRC != c.scheduleCRC:
                        print ('circle mac: %s needs schedule to be uploaded' % (mac,))
                        try:
                            c.schedule_off()
                            c.load_schedule()
                            #update scheduleCRC
                            c.get_clock()
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
                print ('circle mac: %s needs to be switched %s' % (mac, sw_state))
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
                print ('circle mac: %s needs schedule to be switched %s' % (mac, sc_state))
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
        #failure to apply control settings to a certain circle results
        #in offline state for that circle, so it get repaired when the
        #self.test_offline() method detects it is back online
        #a failure to load a schedule data also results in online = False,
        #and recovery is done by the same functions.
             
    def test_offline(self):
        """
        When an unrecoverable communication failure with a circle occurs, the circle
        is set online = False. This function will test on this condition and if offline,
        it test whether it is available again, and if so, it will recover
        control settings and switching schedule if needed.
        In case the circle was offline during intialization, a reinit is performed.
        """
        again_online = False
        for c in self.circles:
            if not c.online:
                try:
                    c.ping()
                    if c.online:
                        #back online. make sure switch and schedule is ok
                        again_online = True
                except ValueError:
                    continue
                except (TimeoutException, SerialException) as reason:
                    error("Error in test_offline(): %s" % (reason,))
                    continue
            if again_online:
                if not c.initialized:
                    c.reinit()
                    self.set_interval_production(c)
                #self.apply_control_changes(force=True)
                idx=self.controlsbymac[c.mac]
                self.apply_control_to_circle(self.controls[idx], c.mac)
                                
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
                #now unsollicted 0061 FFFD messages may arrive from circleplus
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
        #nodes can alse be removed from the table with methods:
        #     cp.remove_node('mac'), where cp is the circleplus object.
        #for demostrative pruposes read and print the table
        print self.circles[0].read_node_table()
      
        #Inform network that nodes are allowed to join the network
        #Nodes may start advertizing themselves with a 0006 message.
        self.device.enable_joining(True)   
        time.sleep(5)
        #0006 may be received
        #Now add the given mac id to the circleplus node table
        self.device.join_node(newnodemac, True)            
        #now unsollicted 0061 FFFD messages may arrive from node if it was in a resetted state
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
        #excpet that now the mac-id of the new node needs to be extracted from
        #the 0006 messages from the node.
        #handling of this is not yet in the api module.
        #a listen method should be added for 0006 messages, which may just result
        #in a timeout when not received.
        
        
    def run(self):
        global day
        global hour
        global minute
        i=self.byname['solar-1710']
        c=self.circles[i]
        #print(c.get_status())
        #pp.pprint(c.get_status(), depth=2)
        self.log_status()
        
        #just some testing at startup
        try:
            c.ping()
            print c.get_info()
            print c.last_log
        except:
            pass
        # for log_idx in range(0,7000):
            # print c.get_power_usage_history_raw(log_idx)
        # print c.get_power_usage_history_raw(6014)
        # print c.get_power_usage_history_raw(6015)
        # print c.get_power_usage_history_raw(0)
        
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
        

        self.test_offline()
        self.poll_configuration()
        try:
            self.device.enable_joining(True)
        except:
            error("PWControl.run(): Communication error in enable_joining") 
            
        if rsyncing:
            print("rsync enabled")
        else:
            print("rsync disabled")

        
main=PWControl()
main.run()









