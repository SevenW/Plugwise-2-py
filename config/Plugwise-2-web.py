#!/usr/bin/env python

# Copyright (C) 2014 Seven Watt <info@sevenwatt.com>
# <http://www.sevenwatt.com>
#
# This file is part of Plugwise-2.
#
# Plugwise-2 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Plugwise-2 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Plugwise-2 If not, see <http://www.gnu.org/licenses/>. 
#

import sys
import time
import logging
import logging.handlers
import string
import cgi
import urlparse
import mimetypes
import os
import glob
import json

import threading
from SocketServer import ThreadingMixIn
from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler

from libraries import *
from libraries.util import *
from libraries.pwmqtt import *
from libraries.HTTPWebSocketsHandler import HTTPWebSocketsHandler
    
cfg = json.load(open("pw-hostconfig.json"))

#global var
pw_logger = None
logpath = cfg['log_path']+'/'
init_logger(logpath+"pw-web.log", "pw-web")
if cfg.has_key('log_level'):
    if cfg['log_level'].strip().lower() == 'debug':
        log_level(logging.DEBUG)
    elif cfg['log_level'].strip().lower() == 'info':
        log_level(logging.INFO)
    elif cfg['log_level'].strip().lower() == 'error':
        log_level(logging.ERROR)
    else:
        log_level(logging.INFO)
        
info('Number of arguments: %d' % (len(sys.argv),))
info('Argument List: %s' % (sys.argv,))

#setup mqtt (if mosquitto bindings are found)
import Queue
import threading
#from pwmqttweb import *

mqtt = True
try:
    import mosquitto
except:
    try:
        import libraries.mosquitto
    except:
        mqtt = False
        
qpub = Queue.Queue()
qsub = Queue.Queue()
mqtt_t = None
if  not mqtt:
    error("No MQTT python binding installed (mosquitto-python)")
elif cfg.has_key('mqtt_ip') and cfg.has_key('mqtt_port'):
    #connect to server and start worker thread.
    mqttclient = Mqtt_client(cfg['mqtt_ip'], cfg['mqtt_port'], qpub, qsub)
    mqttclient.subscribe("plugwise2py/state/#")
    mqtt_t = threading.Thread(target=mqttclient.run)
    mqtt_t.setDaemon(True)
    mqtt_t.start()
    info("MQTT thread started")
    print("MQTT thread started")
else:
    error("No MQTT broker and port configured")
    mqtt = False
    
print("MQTT thread started")

if len(sys.argv) > 1:
    port = int(sys.argv[1])
else:
    port = 8000

 
class PW2PYwebHandler(HTTPWebSocketsHandler):
    def do_GET(self):
        debug("GET " + self.path)
        if self.path in ['', '/', '/index']:
            self.path = '/index.html'
        #for this specific application this entry point:
        if self.path == '/index.html':
            self.path = '/pw2py.html'
        #parse url
        purl = urlparse.urlparse(self.path)
        path = purl.path
        debug("parsed: " + path)
        if path == '/schedules':
            #retrieve list of schedules
            schedules = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob(os.curdir + os.sep + 'schedules/*.json')]
            #print schedules
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(schedules))
            return
        
        #websocket request?
        #websocket url needs to have extension .ws. No test header required
        #elif self.headers.get("Upgrade", None) == "websocket":
        #
        #only allow certain file types to be retrieved
        elif any(path.endswith(x) for x in ('.ws','.html','.js','.css','.png','.jpg','.gif', '.svg', '.ttf', '.woff', '.txt','.map','.json')):
            HTTPWebSocketsHandler.do_GET(self)
        else:
            self.send_error(404,'Plugwise-2-py-web Page not found')


    def do_POST(self):
        #self.logRequest()
                
        path = self.path
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        
        if (ctype == 'application/x-www-form-urlencoded'): 
            clienttype = "ajax    "
        else:
            clienttype = "angular "


        info("%s POST: Path %s" % (clienttype, path))
        debug("%s POST: Content-type %s" % (clienttype, ctype))

        if ((ctype == 'application/x-www-form-urlencoded') or (ctype == 'application/json')):
            if (path.startswith('/schedules/') and path.endswith('.json')) or path == '/pw-control.json':
                #Write a config or schedule JSON file
                debug("POST write a config schedule JSON file")
                length = int(self.headers.getheader('content-length'))
                raw = self.rfile.read(length)
                #print raw
                if (ctype == 'application/x-www-form-urlencoded'):
                    postvars = urlparse.parse_qs(raw, keep_blank_values=1)

                    if 'data' not in postvars:

                        debug("ajaxserver.POST: missing input parameter: %s" % (postvars,))
                        self.send_response(404, "data invalid format")
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({ "error": "missing data parameter" }))
                        return
                    #TODO: check for ajax POST client whether postvars['data'][0] is already the string to write!
                    #print postvars['data'][0]
                    ndata = json.loads(postvars['data'][0])
                    data = json.dumps(data);
                else:
                    data = raw
                #save schedule json file
                fnsched = os.curdir + self.path

                debug("POST save schedule to file path: " + fnsched)
                try:
                    with open(fnsched, 'w') as outfile:
                        #json.dump(data, outfile)
                        outfile.write(data)
                except IOError as err:

                    error("POST exception during saving schedule: %s" % (err,))
                    self.send_error(404,'Unable to store: %s' % fnsched)
                    return
                
                self.send_response(200, "ok")
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({ "result": "ok"}))
                return
            elif path == '/schedules':
                length = int(self.headers.getheader('content-length'))
                raw = self.rfile.read(length)
                debug("POST delete schedule %s" % (json.loads(raw)['delete'],))
                
                try:
                    fnsched = path[1:]+"/"+json.loads(raw)['delete']
                    os.remove(fnsched)
                except OSError:
                    self.send_error(404,'Unable to remove: %s' % fnsched)
                    return
                self.send_response(200, "ok")
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({ "result": "ok"}))
                return
            elif path == '/mqtt/':
                length = int(self.headers.getheader('content-length'))
                raw = self.rfile.read(length)
                data = json.loads(raw)
                info("POST mqtt message: %s" % data)
                topic = str(data['topic'])
                msg = json.dumps(data['payload'])
                qpub.put((topic, msg))
                self.send_response(200, "ok")
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({ "result": "ok"}))
                return

        
        info("POST unhandled. Send 404.")
        self.send_response(404, "unsupported POST")
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({ "error": "only accepting application/json or application/x-www-form-urlencoded" }))
        return
 
    def on_ws_message(self, message):
        if message is None:
            message = ''
        # # echo message back to client
        # self.send_message(str(message))
        self.log_message('websocket received "%s"',str(message))
        try:
            data = json.loads(message)
            topic = str(data['topic'])
            payload = json.dumps(data['payload'])
            qpub.put((topic, payload))
        except Exception as err:
            print("Error parsing incoming websocket message: %s", err)

    def on_ws_connected(self):
        self.log_message('%s','websocket connected')
        self.t = threading.Thread(target=self.process_mqtt)
        self.t.daemon = True
        self.t.start()

    def on_ws_closed(self):
        self.log_message('%s','websocket closed')
        
    def process_mqtt(self):
        while self.handshake_done:
            while not qsub.empty():
                rcv = qsub.get()
                topic = rcv[0]
                payl = rcv[1]
                info("process_mqtt_commands: %s %s" % (topic, payl)) 
                if self.handshake_done:
                    self.send_message(payl)
            time.sleep(0.5)
    
    # def handle(self):
        # """Handle multiple requests if necessary."""
        # self.close_connection = 1

        # self.handle_one_request()
        # while not self.close_connection:
            # self.handle_one_request()
 
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
 
def main():
    try:
        server = ThreadedHTTPServer(('', port), PW2PYwebHandler)
        server.daemon_threads = True
        info('started httpserver at port %d' % (port,))
        #process_mqtt_commands()
        server.serve_forever()
    except KeyboardInterrupt:
        print('^C received, shutting down server')
        #server.socket.close()
        server.shutdown()
        print "exit after server.shutdown()"

if __name__ == '__main__':
    main()