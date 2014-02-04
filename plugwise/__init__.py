"""
Library for communicating with Plugwise Circle and Circle+ smartplugs.

There's no official documentation available about these things so this implementation is based
on partial reverse engineering by Maarten Damen (http://www.maartendamen.com/downloads/?did=5)
and several other sources. 

Usage example:

   >>> from plugwise import Stick
   >>> s = Stick(port="/dev/ttyUSB0")
   >>> c1, c2 = Circle(mac1, s), Circle(mac2, s)
   >>> c1.switch_on()
   >>> print c2.get_power_usage()
   >>> c1.switch_off()

"""

from .api import *
