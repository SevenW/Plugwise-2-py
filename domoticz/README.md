Plugwise-2-py - Domoticz bridge
===============================

#Installation
- Make sure NodeRed is installed. See Domoticz WIKI.
- In Domoticz a (hardware) MQTT gateway needs to be defined. See Domoticz WIKI
- In Domoticz create a Dummy hardware device and call it "VirtualPlugwise-2-py". Make a note of its hardware id.
- Copy the content of plugwise2py-domoticz.nodered to NodeRed. Top-right corner in NodeRed webpage, select Import -> Clipboard. Paste the text.
- MQTT defaults to 127.0.0.1:1883. If needed enter the right MQTT broker into the three MQTT related nodes in NodeRed.
- Edit the first few lines in the node "initialise global context". The default ip and port of domoticz might be right, but the HW id of the Dummy hardware for the virtual switches/sensors needs to be entered.
