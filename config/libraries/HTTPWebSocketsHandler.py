'''
The MIT License (MIT)

Copyright (C) 2014, 2015 Seven Watt <info@sevenwatt.com>
<http://www.sevenwatt.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

from SimpleHTTPServer import SimpleHTTPRequestHandler
import struct
from base64 import b64encode
from hashlib import sha1
from mimetools import Message
from StringIO import StringIO
import socket #for timeout exception

class HTTPWebSocketsHandler(SimpleHTTPRequestHandler):
    magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    
    def on_ws_message(self, message):
        """Override this handler to process incoming websocket messages."""
        pass
        
    def on_ws_connected(self):
        """Override this handler."""
        pass
        
    def on_ws_closed(self):
        """Override this handler."""
        pass
        
    def setup(self):
        #self.timeout = 60
        SimpleHTTPRequestHandler.setup(self)
        #self.log_message('Websocket capable connection with %s',str(self.client_address))
        self.handshake_done = False
                
    def handle_one_request(self):
        #try:
            if self.handshake_done:
                self.read_next_message()
                #a read or a write timed out.  Discard this connection
            else:
                SimpleHTTPRequestHandler.handle_one_request(self)
        # except socket.timeout, e:
            # # print("handle_one_request() socket timed out: %s", e)
            # pass
                          
    def checkAuthentication(self):
        auth = self.headers.get('Authorization')
        if auth != "Basic %s" % self.server.auth:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="webdev"')
            self.end_headers();
            return False
        return True

    def do_GET(self):
        if self.server.auth and not self.checkAuthentication():
            return
        if self.headers.get("Upgrade", None) == "websocket":
            self.handshake()
        else:
            SimpleHTTPRequestHandler.do_GET(self)
                          
    def read_next_message(self):
        self.opcode = ord(self.rfile.read(1)) & 0x0F
        length = ord(self.rfile.read(1)) & 127
        if length == 126:
            length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.rfile.read(8))[0]
        masks = [ord(byte) for byte in self.rfile.read(4)]
        decoded = ""
        for char in self.rfile.read(length):
            decoded += chr(ord(char) ^ masks[len(decoded) % 4])
        self.on_message(decoded)

    def send_message(self, message):
        self.request.send(chr(129))
        length = len(message)
        if length <= 125:
            self.request.send(chr(length))
        elif length >= 126 and length <= 65535:
            self.request.send(chr(126))
            self.request.send(struct.pack(">H", length))
        else:
            self.request.send(chr(127))
            self.request.send(struct.pack(">Q", length))
        self.request.send(message)

    def handshake(self):
        headers=self.headers
        if headers.get("Upgrade", None) != "websocket":
            return
        key = headers['Sec-WebSocket-Key']
        digest = b64encode(sha1(key + self.magic).hexdigest().decode('hex'))
        self.send_response(101, 'Switching Protocols')
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', str(digest))
        self.end_headers()
        self.handshake_done = True
        self.close_connection = 0
        self.on_ws_connected()

    def on_message(self, message):
        _stream = 0x0
        _text = 0x1
        _binary = 0x2
        _close = 0x8
        _ping = 0x9
        _pong = 0xa

        # close
        if self.opcode == _close:
         self.send_close()
         self.handshake_done = False
         self.connection_close = 1
         self.on_ws_closed()
        # ping
        elif self.opcode == _ping:
         pass
        # pong
        elif self.opcode == _pong:
         pass
        # data
        elif self.opcode == _stream or self.opcode == _text or self.opcode == _binary:
         self.on_ws_message(message)

    def send_close(self):
        msg = bytearray()
        msg.append(0x88)
        msg.append(0x00)
        self.request.send(msg)
