#!/usr/bin/python3
# EmonHubSofarSolarManInterfacer released for use by OpenEnergyMonitor project
# GNU GENERAL PUBLIC LICENSE -  Version 2, June 1991
# See LICENCE and README file for details

__author__ = 'Dan Conlon'

import sys
import time
import traceback
import requests
import Cargo
from emonhub_interfacer import EmonHubInterfacer

"""class EmonHubSofarSolarManInterfacer

Fetch metrics from Solax inverter via WiFi dongle

"""

class EmonHubSolaxSolarInterfacer(EmonHubInterfacer):

    def __init__(self, name, host, password, pollinterval, nodeid=30):
        """Initialize interfacer"""

        # Initialization
        super().__init__(name)

        self._NodeName = name
        self._NodeId = int(nodeid)
        self._host = host
        self._password = password
        self._poll_interval = int(pollinterval)

        self._next_poll_time = None

    def close(self):
        return None
        
    def _set_poll_timer(self, seconds):
        self._next_poll_time = time.time() + seconds

    def _is_it_time(self):
        if not self._next_poll_time: # First time loop
            return True
            
        return time.time() > self._next_poll_time

    # Override base _process_rx code from emonhub_interfacer
    def _process_rx(self, rxc):
        if not rxc:
            return False

        return rxc

    # Override base read code from emonhub_interfacer
    def read(self):
        """Read data from inverter"""

        # Wait until we are ready to fetch
        if not self._is_it_time():
            return

        cargo = None

        try:
            cargo = self._fetch_from_inverter()

            # Poll timer reset after successful fetch
            self._set_poll_timer(self._poll_interval)

        except Exception as err2:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._log.error(err2)
            self._log.debug(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            self.close()
            self._set_poll_timer(10) # Retry in 10 seconds

        return cargo

    def _fetch_from_inverter(self):
        r = requests.post("http://" + self._host, data={"optType": "ReadRealTimeData", "pwd": self._password})

        if r.status_code != 200:
            raise Exception(f"Couldn't fetch data from inverter ({r.status_code})")
        
        data = None
        try:
            body = r.json()
            data = body['Data']
        except Exception as e:
            raise Exception(f"Invalid data from inverter: {r.content}")
    
        
        def read16BitSigned(n):
          if n < 32768:
            return n
          else:
            return n - 65536
    
        stats = {
            "ac_voltage": data[0] / 10,
            "ac_current" : read16BitSigned(data[1]) / 10,
            "ac_frequency": data[2] / 100,
            "ac_power": read16BitSigned(data[3]),
        
            "dc_power_string1": data[13],
            "dc_power_string2": data[14],
            "dc_voltage_string1": data[4] / 10,
            "dc_voltage_string2": data[5] / 10,
            "dc_current_string1": data[8] / 10,
            "dc_current_string2": data[9] / 10        
        }

        # Cargo object for returning values
        c = Cargo.new_cargo()
        c.rawdata = None
        c.realdata = stats.values()
        c.names = stats.keys()
        c.nodeid = self._NodeId
        c.nodename = self._NodeName

        return c
