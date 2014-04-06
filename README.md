Plugwise-2-py
=============

A version 2.0 of a plugwise python interface and controller

PW-logger.py is a program is a logger of recorded meterings by plugwise.
It also serves as a controller of the switches, and it can be used to upload
switching/standby schedules to the circles.

The interface to control is a file interface. There are four configuration files:
- pw-hostconfig.json: some host/sserver specific settings.
- plugwise.cfg: intended as static configuration of the plugs.
- plugwise_control.csv: dynamic configuration.
- schedule.csv: contains one or more week-schedules to switch the plugs on and off.

Changes to the two .csv files are automatically picked up by PW-logger.py and applied.

A couple of interesting options in the static configuration:
- The in-circle logging interval can be controlled in steps of minutes. Default is 60 minutes. For solar panels I use two minutes.
- By default circles only record consumption. It can be configured to log production as well.
- There is a always on option, which cannot be overridden by switching or schedules. Useful for solar panels. Switching those circles of does not only prevent recording the production, but also takes them of the grid.

In the dynamic configuration:
- logging of the in-circle integrated values can be enabled (usually the one-value-per-hour loggings.
- logging of the actual power (production and or consumption) can  be logged. This value will be logged every 10 seconds.
- switching schedules can be enabled and disabled.

Finally the code implements several commands that have not been published before, at least not in 2012.

Besides the new functions for logging and control purposes, there are major improvements in the robustness of the communication. Return status is checked and acted upon correctly. Replies are now correlated to messages, so that no mix-up occur.

Currently this is a quick publication of the work that I have mainly done in 2012.

Setup
-----
installation:
```wget https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py -O - | sudo python```

```git clone https://github.com/SevenW/Plugwise-2-py.git```
```cd Plugwise-2-py```
```sudo python setup.py install```

config:

In pw-hostconfig.json edit tmp_path, permanent_path and serial
```{"permanent_path": "/home/pi/datalog", "tmp_path": "/tmp", "serial": "/dev/ttyUSB0"}```

Edit the proper circle mac addresses in plugwise.cfg and plugwise_control.csv. Make more changes as appropriate to your needs.

run:

```nohup python PW-logger.py >>/tmp/pwout.log&```

