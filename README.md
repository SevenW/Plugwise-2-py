Plugwise-2-py
=============
v2.0 runs on Python3. Python 2.7 is no longer supported, but can be found as v1.1
-------------
Please submit an issue when stability issues occur.


#Key features:
- Web-interface to switch, configure and edit schedules and stand-by killer
- MQTT interface for control and log meter readings.
- Log every 10-seconds in monitoring mode.
- Read and log Circle metering buffers.
- Change interval of Circle metering buffers, e.g. every 2 minutes.
- Enable production metering for e.g. PV solar energy.
- Always-on option, cannot be overridden by switch command.
- Robust matching of commands and replies in Zigbee communication.
- Openhab interface through MQTT.
- Domoticz interface through MQTT.
- Homey interface through MQTT.
- Home Assistant interface through MQTT.

##Introduction
Plugwise-2-py evolved in a monitoring and control server for plugwise devices.
In v2.0 it can connect to a MQTT server. Commands to for example switch on a light can be given through the MQTT server, and when enabled, power readings are published as MQTT topics.
Plugwise-2.py is a program is a logger of recorded meterings by plugwise.
It also serves as a controller of the switches, and it can be used to upload
switching/standby schedules to the circles.

The interface to control is a file interface. There are three configuration files:
- pw-hostconfig.json: some host/server specific settings.
- pw-conf.json: intended as static configuration of the plugs.
- pw-control.json: dynamic configuration.

Switching / stand-by killer schedules are defines as json files in the schedules folder
- schedules/*.json: contains a week-schedule to switch the plugs on and off.

Changes to pw-control.json and schedules/*.json are automatically picked up by Plugwise-2.py and applied.

pw-control.json and schedules/*.json can be edited with the web application (see below)

In the dynamic configuration:
- logging of the in-circle integrated values can be enabled (usually the one-value-per-hour loggings.
- logging of the actual power (production and or consumption) can  be logged. This value will be logged every 10 seconds.

Finally the code implements several commands that have not been published before, at least not in 2012.

Besides the new functions for logging and control purposes, there are major improvements in the robustness of the communication. Return status is checked and acted upon correctly. Replies are now correlated to messages, so that no mix-up occur.


Setup
-----

```shell
wget https://bootstrap.pypa.io/get-pip.py
sudo python get-pip.py

git clone https://github.com/SevenW/Plugwise-2-py.git
cd Plugwise-2-py
sudo pip install .
```
> Note: include the period "." in the line above!

##configuration:
*First time install*

Template config files are provided in the `config-default` folder. Those can be copied to the `config` folder. Be careful not to overwrite earlier settings.

```shell
#from Plugwise-2-py folder:
cp -n config-default/pw-hostconfig.json config/
cp -n config-default/pw-control.json config/
cp -n config-default/pw-conf.json config/
```

*configuring server and circles*

In config/pw-hostconfig.json edit tmp_path, permanent_path, log_path and serial

```{"permanent_path": "/home/pi/datalog", "tmp_path": "/tmp", "log_path": "/home/pi/pwlog", "serial": "/dev/ttyUSB0"}```

> Note: For INFO/DEBUG logging, normally /var/log can be used as path. However, on the raspberry pi, only the root user can write in /var/log. Therefore it is better to log to /home/<username>/pwlog

> Note: Editing JSON files is error-prone. Use a JSON Validator such as http://jsonlint.com/ to check the config files.

Edit the proper Circle mac addresses in pw-conf.json and pw-control.json. Make more changes as appropriate to your needs.
- Enable 10-seconds monitoring: `"monitor": "yes"`
- Enable logging form Circle internal metering buffers: `"savelog": "yes"`

Note: At first start-up, it starts reading the Circle internal metering buffers form position zero up to the current time. Worst case it can read for three years worth of readings. This may take form several minutes to several hours.
Monitor this activity by tailing the log file:

`tail -f /home/pi/pwlog/pw-logger.log`

MQTT can be enable by adding two key,values to pw-hostconfig.json

`"mqtt_ip": "127.0.0.1", "mqtt_port": "1883"`

An example config file can be found in pw-hostconfig-mqtt.json

Plugwise-2-py provides a MQTT-client. A separate MQTT-server like Mosquitto needs to be installed to enable MQTT in Plugwise-2-py. On Ubuntu systems it can be done like this:

`sudo apt-get install mosquitto`

The default port is 1883.

##run:

```nohup python Plugwise-2.py >>/tmp/pwout.log&```

##autostart:
Plugwise-2-py and the web-server can be automatically started with upstart in Ubuntu, or a cron job on the Raspberry pi. See instructions in the `autostart-howto` folder.

##debug:
the log level can be programmed in pw-control.json. Changes are picked up latest after 10 seconds.

`"log_level": "info"` can have values error, info, debug

`"log_comm": "no"` can have values no and yes.

log_comm results in logging to  pw-communications.log, in the log folder specified through log_path in pw-hostconfig.json

Update from github
------------------
```shell
#from Plugwise-2-py folder:
git pull
sudo pip install --upgrade .
```

Web interface
-------------
Plugwise-2-py can be operated through a web interfaces. The packages comes with its own dedicated web-server also written in python. It makes use of websockets for efficient and unsolicited communication.
##setup

```shell
#assume current directory is Plugwise-2-py main directory
nohup python Plugwise-2-web.py 8000 secure plugwise:mysecret >>pwwebout.log&
```

This uses SSL/https. Change plugwise:mysecret in a username:password chosen by yourself. The websserver uses port 8000 by default, and can be changed by an optional parameter:

`nohup python Plugwise-2-web.py 8001 secure plugwise:mysecret >>pwwebout.log&`

Providing a user:password is optional, as well as using SSL/https. When the website is only accessible within your LAN, then the server can be used as plain http, by omitting the secure parameter. The following parameter formats are valid:

```shell
nohup python Plugwise-2-web.py 8001 secure user:password >>pwwebout.log&

#no username and password requested
nohup python Plugwise-2-web.py 8000 secure >>pwwebout.log&

#plain http, with optional port
nohup python Plugwise-2-web.py 8002 >>pwwebout.log&

#plain http, default port 8000
nohup python Plugwise-2-web.py >>pwwebout.log&
```

##use
###Control (switch and monitor)
type in browser

`https://<ip of the server>:8000`

or

`https://<ip of the server>:8000/pw2py.html`

for example:

`http://localhost:8000/pw2py.html`

in case of SSL/secure: use https//:

`https://localhost:8000/pw2py.html`

###Configure and edit schedules
(No editing static configuration file supported yet)
type in browser:

`http://<ip of the server>:8000/cfg-pw2py.html`

for example:

`http://localhost:8000/cfg-pw2py.html`


##require
The Control web-application requires the MQTT connection to be operational. The configuration application can work without MQTT.

MQTT
----
##power readings
power readings can be published
- autonomous
- on request

###Autonomous
Autonomous messages are published when monitoring = "yes" and when savelog = "yes". The 10-seconds monitoring published messages:

`plugwise2py/state/power/000D6F0001Annnnn {"typ":"pwpower","ts":1405452425,"mac":"000D6F0001Annnnn","power":9.78}`

The readings of the Circle buffers are published as:

`plugwise2py/state/energy/000D6F0001Annnnn {"typ":"pwenergy","ts":1405450200,"mac":"000D6F0001nnnnnn","power":214.2069,"energy":35.7012,"interval":10}`

###On request
From applications like openhab, a power reading can be requested when needed, or for example scheduled by a cron job. The request will return a full circle state including the short term (8 seconds) integrated power value of the circle. Requests:

`plugwise2py/cmd/reqstate/000D6F00019nnnnn {"mac":"","cmd":"reqstate","val":"1"}`

in which val and mac can be an arbitrary values.
The response is published as:

`plugwise2py/state/circle/000D6F00019nnnnn {"powerts": 1405452834, "name": "circle4", "schedule": "off", "power1s": 107.897, "power8s": 109.218, "readonly": false, "interval": 10, "switch": "on", "mac": "000D6F00019nnnnn", "production": false, "monitor": false, "lastseen": 1405452834, "power1h": 8.228, "online": true, "savelog": true, "type": "circle", "schedname": "test-alternate", "location": "hal1"}`

##controlling switches and schedules
Circles can be switched by publishing a command:

`plugwise2py/cmd/switch/000D6F0001Annnnn {"mac":"","cmd":"switch","val":"on"}`

or

`plugwise2py/cmd/schedule/000D6F0001Annnnn {"mac":"","cmd":"schedule","val":"on"}`


The circle does respond with a state message, from which it can be deduced whether switching has been successful

`plugwise2py/state/circle/000D6F0001Annnnn {.... "schedule": "off", "switch": "on" ....}`

Openhab
-------
Openhab can communicate with Plugwise-2-py through a MQTT server. Openhab provides a convenient system to operate switches and schedules. Also it can be used to record power readings and draw some graphs.

TODO: Add a description.
Example sitemap, items, rules and transforms can be found in the openhab folder in this repository

Domoticz
--------
A MQTT to HTTP commands interface (using Node-Red) has been developed:
https://www.domoticz.com/forum/viewtopic.php?f=14&t=7420&sid=22502c728a9a4f7d5ac93e6f5c0642a9

I am investigating a more direct MQTT to Domoticz interface currently.

Homey
--------
A Homey app is available in the appstore: https://apps.athom.com/app/com.gruijter.plugwise2py

For further instructions please visit https://forum.athom.com/discussion/1998

Home Assistant
--------
Interfacing with Home Assistant can be done through MQTT.

Some examples:
```
sensor:
 - platform: mqtt
   name: Coffee
   state_topic: 'plugwise2py/state/power/000D6F000XXXXXXX'
   unit_of_measurement: 'W'
   value_template: '{{ value_json.power }}'
   sensor_class: power
```
```
switch:
 - platform: mqtt
   name: Coffee
   optimistic : false
   command_topic: 'plugwise2py/cmd/switch/000D6F000XXXXXXX'
   state_topic: 'plugwise2py/state/circle/000D6F000XXXXXXX'
   value_template: '{"mac": "000D6F000XXXXXXX", "cmd": "switch", "val": "{{ value_json.switch }}"}'
   payload_on: '{"mac": "000D6F000XXXXXXX", "cmd": "switch", "val": "on"}'
   payload_off: '{"mac": "000D6F000XXXXXXX", "cmd": "switch", "val": "off"}'
   retain: true
```
```
binary_sensor:
 - platform: mqtt
   name: 'Plugwise Cicle Status for Coffee'
   state_topic: 'plugwise2py/state/circle/000D6F000XXXXXXX'
   sensor_class: connectivity
   value_template: '{{ value_json.online }}'
   payload_on: True
   payload_off: False
```

