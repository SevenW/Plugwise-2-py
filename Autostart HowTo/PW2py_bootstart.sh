cd /home/pi/Plugwise-2-py
nohup python Plugwise-2.py >>/tmp/pwout.log&
nohup python Plugwise-2-web.py >>pwwebout.log&
