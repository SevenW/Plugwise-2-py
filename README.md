Plugwise-2-py
=============

#Key features:
- MQTT interface for control and log meter readings.
- Log every 10-seconds in monitoring mode.
- Read and log Circle metering buffers.
- Change interval of Circle metering buffers, e.g. every 2 minutes.
- Enable production metering for e.g. PV solar energy.
- Always-on option, cannot be overridden by switch command.
- Robust matching of commands and replies in Zigbee communication.
- Openhab interface through MQTT.

##Introduction
Plugwise-2-py evolved in a monitoring and control server for plugwise devices.
In v2.0 it can connect to a MQTT server. Commands to for example switch on a light can be given through the MQTT server, and when enabled, power readings are published as MQTT topics.
Plugwise-2.py is a program is a logger of recorded meterings by plugwise.
It also serves as a controller of the switches, and it can be used to upload
switching/standby schedules to the circles.

The interface to control is a file interface. There are four configuration files:
- pw-hostconfig.json: some host/server specific settings.
- pw-conf.json: intended as static configuration of the plugs.
- pw-control.json: dynamic configuration.
- pw-schedules.json: contains one or more week-schedules to switch the plugs on and off.

Changes to pw-control.json and pw-schedules.json are automatically picked up by Plugwise-2.py and applied.

In the dynamic configuration:
- logging of the in-circle integrated values can be enabled (usually the one-value-per-hour loggings.
- logging of the actual power (production and or consumption) can  be logged. This value will be logged every 10 seconds.
- switching schedules can be enabled and disabled.

Finally the code implements several commands that have not been published before, at least not in 2012.

Besides the new functions for logging and control purposes, there are major improvements in the robustness of the communication. Return status is checked and acted upon correctly. Replies are now correlated to messages, so that no mix-up occur.


Setup
-----
installation:

```
wget https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py -O - | sudo python```

git clone https://github.com/SevenW/Plugwise-2-py.git
cd Plugwise-2-py
sudo python setup.py install
```

##config:

In pw-hostconfig.json edit tmp_path, permanent_path, log_path and serial

```{"permanent_path": "/home/pi/datalog", "tmp_path": "/tmp", "serial": "/dev/ttyUSB0"}```

Edit the proper Circle mac addresses in pw-conf.json and pw-control.json. Make more changes as appropriate to your needs.
- Enable 10-seconds monitoring: `"monitor": "yes"`
- Enable logging form Circle internal metering buffers: `"savelog": "yes"`

Note: At first start-up, it starts reading the Circle internal metering buffers form position zero up to the current time. Worst case it can read for three years worth of readings. This may take form several minutes to several hours.
Monitor this activity bu tailing the log file:

`tail -f /var/log/pw-logger.log`

MQTT can be enable by adding two key,values to pw-hostconfig.json

`"mqtt_ip": "127.0.0.1", "mqtt_port": "1883"`

An example config file can be found in pw-hostconfig-mqtt.json

Plugwise-2-py provides a MQTT-client. A separate MQTT-server like Mosquitto needs to be installed to enable MQTT in Plugwise-2-py. On Ubuntu systems it can be done like this:

`sudo apt-get install mosquitto`

The default port is 1883.

##run:

```nohup python Plugwise-2.py >>/tmp/pwout.log&```

##debug:
the log level can be programmed in pw-control.json. Changes are picked up latest after 10 seconds.

`"log_level": "info"` can have values error, info, debug

`"log_comm": "no"` can have values no and yes. 

log_comm results in logging to  pw-communications.log, in the log folder specified through log_path in pw-hostconfig.json

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

`plugwise2py/state/energy/000D6F0001Annnnn {"typ":"pwenergy","ts":1405450200,"mac":"000D6F00019E1A1E","power":214.2069,"energy":35.7012,"interval":10}`

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

