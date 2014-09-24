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
import string,cgi,time
import os
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import mimetypes
import json
import urlparse
#import urllib #can be used to unquote HTTP payload
import glob

#setup logging
def init_logger(logfname, appname='plugwise-2-web'):
    global pw_logger
    pw_logger = logging.getLogger(appname)
    log_level()
    # Add the log message handler to the logger
    handler = logging.handlers.RotatingFileHandler(logfname, maxBytes=50000, backupCount=3)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    pw_logger.addHandler(handler)
    pw_logger.info("logging started")
   
def log_level(level=logging.DEBUG):
    pw_logger.setLevel(level)

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

if len(sys.argv) > 1:
    port = int(sys.argv[1])
else:
    port = 8000
    
class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            debug("GET " + self.path)
            if self.path in ['', '/', '/index']:
                self.path = '/index.html'
            #for this sprecific application this entry point:
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
            #only allow certain file types to be retrieved
            elif ((path.startswith('/schedules/') and path.endswith('.json')) or
                    any(path.endswith(x) for x in ('.html','.js','.css','.jpg','.gif', '.svg', '.ttf', '.woff', '.txt','.map'))):
                f = open(os.curdir + os.sep + path) 
                self.send_response(200)
                self.send_header('Content-type', mimetypes.guess_type(path)[0])
                self.end_headers()
                self.wfile.write(f.read())
                f.close()
                return
            else:
                self.send_error(404,'Page not found')
        except IOError:
            self.send_error(404,'File Not Found: %s' % self.path)


















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
            if (path.startswith('/schedules/') and path.endswith('.json')):


                #Write a schedule JSON file
                debug("POST write a schedule JSON file")
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
 
        
        info("POST unhandled. Send 404.")
        self.send_response(404, "unsupported POST")
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({ "error": "only accepting application/json or application/x-www-form-urlencoded" }))
        return
                    
def main():
    try:
        server = HTTPServer(('', port), MyHandler)
        info('started httpserver at port %d' % (port,))
        server.serve_forever()
    except KeyboardInterrupt:
        error('^C received, shutting down server')
        server.socket.close()

if __name__ == '__main__':
    main()