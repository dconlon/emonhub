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

        self._information_params = {
            '11':  'circulation_pump_state', # 1 = pump stopped, 0 = pump running
            '12':  'target_flow_temp',
            '13':  'is_space_heating', # 0 is HW, 1 is CH
            '14':  'flow_temp', 
            '15':  'return_temp',
            '21':  'compressor_frequency',
            '22':  'unknown_information_22',
            '23':  'ambient_temp_heatpump',
            '24':  'unknown_information_24', # flow_temp
            '25':  'unknown_information_25', # return_temp
            '22':  'fan_speed',
            '26':  'no_heat_demanded', # 1 - no heat demanded, 0 - heat demanded
            '61':  'dhw_temp',
            '71':  'unknown_information_71', #  could be buffer_temp_top
            '72':  'unknown_information_72', # seems same as 81 and TempBuforDownreturn temp or buffer_temp_bottom
            '91':  'unknown_information_91',
            '92':  'unknown_information_92', # follows but lags behind return_temp, could be a temp probe
            '93':  'circuit1_target_flow_temp',
            '101': 'circuit2_measured_temp', # overall ch flow temp, TempCircuit2
            '111': 'circuit3_measured_temp', # boiler flow temp, TempCircuit3
            '181': 'touchscreen_firmware_version',
            '182': 'controller_firmware_version',
            '184': 'uid',
            '185': 'serial_number',
            '211': 'input_power', # not working
            '212': 'output_power', # not working
            '221': 'cop', # not working
            '222': 'scop', # not working
            '243': 'unknown_information_243', # follows but lags behind return_temp
            '244': 'unknown_information_244',
        }

        self._data_params = {
            '14': 'actual_flow_temp',
            '24': 'actual_flow_temp',
            '91': 'actual_flow_temp',
            '119': 'dhw_work_mode', # 0 is off, 1 is on, 2 is scheduled
            '103': 'dhw_setpoint',
            '104': 'dhw_hysteresis',
            '111': 'touchscreen_ambient_temp', # to check
            '115': 'dhw_boost',
            '136': 'dhw_legionella_setpoint',  # Legionella protection temperature (60-80°C)
            '137': 'dhw_legionella_day',       # Legionella protection day of week (0-6)
            '138': 'dhw_legionella_hour',      # Legionella protection hour (0-23)
            '236': 'circuit1_work_mode', # 0 is off, 1 is day, 2 is night, 3 is scheduled
            '238': 'circuit1_day_setpoint',
            '239': 'circuit1_night_setpoint',
            '240': 'circuit1_hysteresis',
            '273': 'circuit1_weather_curve',
            '275': 'circuit1_weather_curve_shift',
            '702': 'summer_on_temp',  # Outdoor temp threshold to activate summer mode (26-30°C)
            '703': 'Summer_off_temp',  # Outdoor temp threshold to deactivate summer mode (0-26°C)
            '1211': 'flow_rate',
            '10413': 'touchscreen_temp_correction', #?

            '69': 'unknown_data_69', # 85-87 "TempSettings"
            '1219': 'fan_speed', # 645-660-765 Looks like fan speed
            '1307': 'unknown_data_1307', # 352, 678-697 roughly follows OAT
        }

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

            for (key, value) in body['informationParams'].items():
                value = value[1][0][0]
                if key in self._information_params:
                    name = self._information_params[key]
                    data[name] = value
                else:
                    print(f"unknown information {key}: {value}")

            for (key, value) in body['data'].items():
                value = value['value']
                if key in self._data_params:
                    name = self._data_params[key]
                    data[name] = value
                else:
                    print(f"unknown data {key}: {value}")

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
