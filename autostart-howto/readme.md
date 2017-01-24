##Autostart Plugwise-2-py
To make Plugwise-2-py autostart after a system(re)boot you can run a script
with cron. Below are the steps for a raspberry pi, where the standard user in
Raspbian is 'pi', and where the Plugwise-2-py webinterface is running unsecure
without password.

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
