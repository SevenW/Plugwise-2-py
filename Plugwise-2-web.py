#!/usr/bin/env python3

# Copyright (C) 2012,2013,2014,2015,2016,2017,2018,2019,2020 Seven Watt <info@sevenwatt.com>
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
import urllib.parse
import mimetypes
import os
import glob
import json

import threading
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler
import ssl
from base64 import b64encode

from swutil import *
from swutil.util import *
from swutil.pwmqtt import *
from swutil.HTTPWebSocketsHandler import HTTPWebSocketsHandler
    
#webroot is the config folder in Plugwise-2-py.
#webserver can only serve files from webroot and subfolders.
#the webroot needs to be the current folder
webroot = os.curdir + os.sep + "config" + os.sep
os.chdir(webroot)
cfg = json.load(open("pw-hostconfig.json"))

#global var
pw_logger = None
logpath = cfg['log_path']+'/'
init_logger(logpath+"pw-web.log", "pw-web")
if 'log_level' in cfg:
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
import queue
import threading
#from pwmqttweb import *

mqtt = True
try:
    import paho.mqtt.client as mosquitto
except:
    mqtt = False
        
qpub = queue.Queue()
qsub = queue.Queue()
broadcast = []
last_topics = {}

#bcmutex = threading.Lock()
mqtt_t = None
if  not mqtt:
    error("No MQTT python binding installed (mosquitto-python)")
elif 'mqtt_ip' in cfg and 'mqtt_port' in cfg:
    #connect to server and start worker thread.
    if 'mqtt_user' in cfg and 'mqtt_password' in cfg:
        mqttclient = Mqtt_client(cfg['mqtt_ip'], cfg['mqtt_port'], qpub, qsub,"Plugwise-2-web",cfg['mqtt_user'],cfg['mqtt_password'])
    else:
        mqttclient = Mqtt_client(cfg['mqtt_ip'], cfg['mqtt_port'], qpub, qsub, "Plugwise-2-web")
    mqttclient.subscribe("plugwise2py/state/#")
    mqtt_t = threading.Thread(target=mqttclient.run)
    mqtt_t.setDaemon(True)
    mqtt_t.start()
    info("MQTT thread started")
else:
    error("No MQTT broker and port configured")
    mqtt = False
    
if len(sys.argv) > 1:
    port = int(sys.argv[1])
else:
    port = 8000

if len(sys.argv) > 2:
    secure = str(sys.argv[2]).lower()=="secure"
else:
    secure = False
if len(sys.argv) > 3:
    credentials = str(sys.argv[3]).encode()
else:
    credentials = b""
    
def broadcaster():
    while True:
        while not qsub.empty():
            rcv = qsub.get()
            topic = rcv[0]
            payl = rcv[1]
            #debug("mqtt broadcaster: %s %s" % (topic, payl)) 
            #bcmutex.acquire()
            last_topics[topic] = payl
            for bq in broadcast:
                bq.put(rcv)
            #bcmutex.release()
        time.sleep(0.1)
        
bc_t = threading.Thread(target=broadcaster)
bc_t.setDaemon(True)
bc_t.start()
info("Broadcast thread started")
    
 
class PW2PYwebHandler(HTTPWebSocketsHandler):
    def log_message(self, format, *args):
        if not args:
            debug(self.address_string()+' '+format)
        else:
            debug(self.address_string()+' '+format % args)

    def log_error(self, format, *args):
        error(self.address_string()+' '+format % args)

    def log_request(self, code='-', size='-'):
        #self.log_message('"%s" %s %s', self.requestline, str(code), str(size))
        info(self.address_string()+' "%s" %s %s' % (self.requestline, str(code), str(size)))
                         
    def end_headers(self):
        self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        HTTPWebSocketsHandler.end_headers(self)

    def do_GET(self):
        self.log_message("PW2PYwebHandler do_GET")
        #debug("GET " + self.path)
        if self.path in ['', '/', '/index']:
            self.path = '/index.html'
        #for this specific application this entry point:
        if self.path == '/index.html':
            self.path = '/pw2py.html'
        #parse url
        purl = urllib.parse.urlparse(self.path)
        path = purl.path
        debug("PW2PYwebHandler.do_GET() parsed: " + path)
        if path == '/schedules':
            #retrieve list of schedules
            schedules = [os.path.splitext(os.path.basename(x))[0] for x in glob.glob(os.curdir + os.sep + 'schedules' + os.sep + '*.json')]
            #print schedules
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(schedules))
            return
        #
        #only allow certain file types to be retrieved
        elif any(path.endswith(x) for x in ('.ws','.html','.js','.css','.png','.jpg','.gif', '.svg', '.ttf', '.woff', '.txt','.map','.json')):
            HTTPWebSocketsHandler.do_GET(self)
        else:
            self.send_error(404,'Plugwise-2-py-web Page not found')


    def do_POST(self):
        self.log_message("PW2PYwebHandler do_POST")
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
                    postvars = urllib.parse.parse_qs(raw, keep_blank_values=1)

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
        #self.log_message('websocket received "%s"',str(message))
        try:
            data = json.loads(message)
            topic = str(data['topic'])
            payload = json.dumps(data['payload'])
            qpub.put((topic, payload))
        except Exception as err:
            self.log_error("Error parsing incoming websocket message: %s", err)

    def on_ws_connected(self):
        self.q = queue.Queue()



        self.t = threading.Thread(target=self.process_mqtt)
        self.t.daemon = True
        self.t.start()
        
        #bcmutex.acquire()
        broadcast.append(self.q)
        #bcmutex.release()
        self.log_message("process_mqtt running on worker thread %d" % self.t.ident)

    def on_ws_closed(self):
        #bcmutex.acquire()
        broadcast.remove(self.q)
        #bcmutex.release()
        #join gives issues. threads seems to be reused, so threads end anyways.
        #self.t.join()
        #self.log_message("on_ws_closed websocket closed for handler %s" % str(self))
        
    def process_mqtt(self):
        #allow some time for websockets to become fully operational
        time.sleep(2.0)
        #send last known state to webpage
        topics = list(last_topics.items())
        for topic in topics:
            self.q.put(topic)
        while self.connected:
            while not self.q.empty():
                rcv = self.q.get()
                topic = rcv[0]
                payl = rcv[1]
                info("process_mqtt_commands: %s %s" % (topic, payl)) 
                if self.connected:
                    self.send_message(payl)
            time.sleep(0.5)

        self.log_message("process_mqtt exiting worker thread %d" % self.t.ident)

        
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

def main():
    try:
        server = ThreadedHTTPServer(('', port), PW2PYwebHandler)
        server.daemon_threads = True
        server.auth = b64encode(credentials)
        if secure:
            if sys.hexversion < 0x02071000:
                #server.socket = ssl.wrap_socket (server.socket, certfile='./server.pem', server_side=True, ssl_version=ssl.PROTOCOL_TLSv1_2)
                server.socket = ssl.wrap_socket (server.socket, certfile='./server.pem', server_side=True, ssl_version=ssl.PROTOCOL_TLSv1)
            else:
                ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ctx.load_cert_chain(certfile="./server.pem")
                ctx.options |= ssl.OP_NO_TLSv1
                ctx.options |= ssl.OP_NO_TLSv1_1
                ctx.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
                ctx.set_ciphers('ECDHE-RSA-AES256-GCM-SHA384 ECDHE-RSA-AES256-SHA384 ECDHE-RSA-AES256-SHA')
                server.socket = ctx.wrap_socket(server.socket, server_side=True)
            
            info('started secure https server at port %d' % (port,))
        else: 
            info('started http server at port %d' % (port,))
        server.serve_forever()
    except KeyboardInterrupt:
        print('^C received, shutting down server')
        server.shutdown()
        print("exit after server.shutdown()")

if __name__ == '__main__':
    main()
