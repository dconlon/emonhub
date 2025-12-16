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

        # Known parameters for Grant Aerona R290, many originally identified by:
        #
        #   @GSV3MiaC in https://community.openenergymonitor.org/t/new-heat-pump-grant-r290-hot-water-advice/28254/38
        #
        #   @LeeNuss in https://github.com/LeeNuss/ecoNET-300-Home-Assistant-Integration/tree/1.2.0-a-ecomax360-1
        #
        self._params_map = {
            'circulation_pump_stopped':     ('informationParams', '11'),  # 1 = pump stopped, 0 = pump running
            'target_flow_temp':             ('informationParams', '12'),
            'is_space_heating':             ('informationParams', '13'),  # 0 is HW, 1 is CH
            'flow_temp':                    ('informationParams', '14'),  # duplicated at 24 and data 14, 24, 91
            'return_temp':                  ('informationParams', '15'),  # duplicated at 25
            'compressor_frequency':         ('informationParams', '21'),
            'fan_speed':                    ('informationParams', '22'),  # duplicated at data 1219
            'ambient_temp_heatpump':        ('informationParams', '23'),
            'no_heat_demanded':             ('informationParams', '26'),  # 1 - no heat demanded, 0 - heat demanded
            'dhw_temp':                     ('informationParams', '61'),
            'buffer_temp_top':              ('informationParams', '71'),  # buffer top temp probe, duplicated at 92 and 243
            'circuit1_target_flow_temp':    ('informationParams', '93'),
            'circuit2_measured_temp':       ('informationParams', '101'), # circuit2 temp probe
            'circuit3_measured_temp':       ('informationParams', '111'), # circuit3 temp probe
            'touchscreen_firmware_version': ('informationParams', '181'),
            'controller_firmware_version':  ('informationParams', '182'),
            'uid':                          ('informationParams', '184'),
            'serial_number':                ('informationParams', '185'),
            'input_power':                  ('informationParams', '211'), # not working
            'output_power':                 ('informationParams', '212'), # not working
            'cop':                          ('informationParams', '221'), # not working
            'scop':                         ('informationParams', '222'), # not working
            'dhw_work_mode':                ('data', '119'),              # 0 is off, 1 is on, 2 is scheduled
            'dhw_setpoint':                 ('data', '103'),
            'dhw_hysteresis':               ('data', '104'),
            'dhw_boost':                    ('data', '115'),
            'dhw_legionella_setpoint':      ('data', '136'),              # Legionella protection temperature (60-80°C)
            'dhw_legionella_day':           ('data', '137'),              # Legionella protection day of week (0-6)
            'dhw_legionella_hour':          ('data', '138'),              # Legionella protection hour (0-23)
            'circuit1_work_mode':           ('data', '236'),              # 0 is off, 1 is day, 2 is night, 3 is scheduled
            'circuit1_day_setpoint':        ('data', '238'),
            'circuit1_night_setpoint':      ('data', '239'),
            'circuit1_hysteresis':          ('data', '240'),
            'circuit1_weather_curve':       ('data', '273'),
            'circuit1_weather_curve_shift': ('data', '275'),
            'summer_on_temp':               ('data', '702'),              # Outdoor temp threshold to activate summer mode (26-30°C)
            'summer_off_temp':              ('data', '703'),              # Outdoor temp threshold to deactivate summer mode (0-26°C)
            'flow_rate':                    ('data', '1211'),
            'silent_mode_level':            ('data', '1385'),             # 0 = level 1, 2 = level 2
            'silent_mode':                  ('data', '1386'),             # 0 = off, 2 = scheduled
            'touchscreen_temp_correction':  ('data', '10413'), # to check
            'weather_sensor_temp':          ('regParams', 'TempWthr'),
            'touchscreen_ambient_temp':     ('regParams', 'Circuit1thermostat'), # to check

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
        """Read data from Econet bridge"""

        # Wait until we are ready to fetch
        if not self._is_it_time():
            return

        cargo = None

        try:
            cargo = self._fetch_data()

            # Poll timer reset after successful fetch
            self._set_poll_timer(self._poll_interval)

        except Exception as err2:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._log.error(err2)
            self._log.debug(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            self.close()
            self._set_poll_timer(10) # Retry in 10 seconds

        return cargo

    def _fetch_data(self):
        regParams  = self._econet_http_request("/econet/regParams")
        editParams = self._econet_http_request("/econet/editParams")

        data = {}

        for (name, (location, key) ) in self._params_map.items():
            try:
                if location == 'regParams':
                    value = regParams['curr'][key]
                elif location == 'informationParams':
                    value = editParams['informationParams'][key][1][0][0]
                elif location == 'data':
                    value = editParams['data'][key]['value']
                else:
                    raise Exception(f"Unknown param location {location}")
                data[name] = value
            except Exception as e:
                self._log.warning(f"Unable to retrieve {name}: {e.__class__.__name__} {e}")

        # Cargo object for returning values
        c = Cargo.new_cargo()
        c.rawdata = None
        c.realdata = list(data.values())
        c.names = list(data.keys())
        c.nodeid = self._NodeId
        c.nodename = self._NodeName

        return c

    def _econet_http_request(self, path):
        basic = HTTPBasicAuth(self._username, self._password)

        r = requests.get("http://" + self._host + path, auth=basic)

        if r.status_code != 200:
            raise Exception(f"Couldn't fetch data ({r.status_code})")
        
        try:
            body = r.json()
            return body
        except Exception as e:
            raise Exception(f"Invalid data from path: {r.content}")