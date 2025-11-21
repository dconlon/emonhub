#!/usr/bin/python3
# EmonHubEconet300Interfacer released for use by OpenEnergyMonitor project
# GNU GENERAL PUBLIC LICENSE -  Version 2, June 1991
# See LICENCE and README file for details

__author__ = 'Dan Conlon'

import sys
import time
import traceback
import requests
import Cargo
from emonhub_interfacer import EmonHubInterfacer
from requests.auth import HTTPBasicAuth


"""class EmonHubEconet300Interfacer

Fetch metrics from Econet300 bridge (as used on Grant heat pumps)

"""

class EmonHubEconet300Interfacer(EmonHubInterfacer):

    def __init__(self, name, host, username, password, pollinterval, nodeid=30):
        """Initialize interfacer"""

        # Initialization
        super().__init__(name)

        self._NodeName = name
        self._NodeId = int(nodeid)
        self._host = host
        self._username = username
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
            cargo = self._fetch()

            # Poll timer reset after successful fetch
            self._set_poll_timer(self._poll_interval)

        except Exception as err2:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._log.error(err2)
            self._log.debug(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            self.close()
            self._set_poll_timer(10) # Retry in 10 seconds

        return cargo

    def _fetch(self):
        basic = HTTPBasicAuth(self._username, self._password)

        r = requests.get("http://" + self._host + "/econet/regParams", auth=basic)

        if r.status_code != 200:
            raise Exception(f"Couldn't fetch data ({r.status_code})")
        
        data = None
        try:
            body = r.json()
            data = body['curr']
        except Exception as e:
            raise Exception(f"Invalid data from regParams: {r.content}")

        # Additional properties from editParams
        r = requests.get("http://" + self._host + "/econet/editParams", auth=basic)
        if r.status_code != 200:
            raise Exception(f"Couldn't fetch data ({r.status_code})")
        
        try:
            body = r.json()
            data['FanSpeed'] = body['informationParams']['22'][1][0][0]
            data['TargetLWT'] = body['informationParams']['12'][1][0][0]
            data['Circuit1DesiredLWT'] = body['informationParams']['93'][1][0][0]
            data['FlowRate'] = body['data']['1211']['value']

        except Exception as e:
            raise Exception(f"Invalid data from editParams: {r.content}")

        print(data)


        # Cargo object for returning values
        c = Cargo.new_cargo()
        c.rawdata = None
        c.realdata = list(data.values())
        c.names = list(data.keys())
        c.nodeid = self._NodeId
        c.nodename = self._NodeName

        return c
