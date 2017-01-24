#Autostart Plugwise-2-py
There are different ways to get Plugwise-2-py and the web-applicaiton automatically started. The first is using the upstart mechanism supported by Ubuntu. The second is using a shell script that is activated by a cron job

##1. Upstart
Install the files `plugwise2py.conf` and `plugwise2py-web.conf` in the folder `/etc/init`, by just copying them to that location.
Edit in both files the user credentials as indicated by the comments preceded by "#SET". This concerns linux user name and group under which the program should run. It is not advised to run as root. Also the install path of Plugwise-2-py needs to be correct. Usually this is in the home folder of the user. finally, the location of the python executable needs to be checked.
In the example for Plugwise-2-web.py, the web-server is configured to use a secure connection, so one needs to enter proper user credentials here.
Service can now be started, stopped or restarted with the following commands:
```
sudo service plugwise2py start
sudo service plugwise2py stop
sudo service plugwise2py restart

sudo service plugwise2py-web start
sudo service plugwise2py-web stop
sudo service plugwise2py-web restart
```
Both services are automatically started at a (re)boot.

##2. Cron job
To make Plugwise-2-py autostart after a system(re)boot you can run a script with cron. Below are the steps for a raspberry pi, where the standard user in Raspbian is 'pi', and where the Plugwise-2-py webinterface is running unsecure without password.

```
cd /home/pi/Plugwise-2-py
nano PW2py_bootstart.sh
# or copy PW2py_bootstart.sh to /home/pi/Plugwise-2-py
# Content of PW2py_bootstart.sh:
#    cd /home/pi/Plugwise-2-py
#    nohup python Plugwise-2.py >>/tmp/pwout.log&
#    nohup python Plugwise-2-web.py >>pwwebout.log&

# modify the rights so that it really works when cron runs the script!
chmod u+x PW2py_bootstart.sh

# modify crontab to run the script
crontab -e
# At the end of the crontab file add this line:
#    @reboot /home/pi/Plugwise-2-py/PW2py_bootstart.sh
```
