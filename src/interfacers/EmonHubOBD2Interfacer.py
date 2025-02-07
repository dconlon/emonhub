#!/usr/bin/python3
# EmonHubOBD2Interfacer released for use by OpenEnergyMonitor project
# GNU GENERAL PUBLIC LICENSE -  Version 2, June 1991
# See LICENCE and README file for details

__author__ = 'Dan Conlon'

import sys
import time
import traceback
import json
import Cargo
from emonhub_interfacer import EmonHubInterfacer

# Need's fork of python-OBD which connects over TCP instead of UART: https://github.com/dailab/python-OBD-wifi/tree/master
import obd
from obd.OBDCommand import OBDCommand
from obd.decoders import percent, uas
from obd.protocols import ECU

"""class EmonHubOBD2Interfacer

Fetch metrics from car via ODB2 WiFi Dongle

"""

class EmonHubOBD2Interfacer(EmonHubInterfacer):
    
    class OBDPrivate(obd.OBD):
        def _OBD__load_commands(self):
            # Don't waste time loading supported commands, we know the ones we will send are supported
            # and will send with force=True so python-OBD does not check if they are supported
            pass
    

    def __init__(self, name, host, port=35000, pollinterval=60, nodeid=30):
        """Initialize interfacer"""

        # Initialization
        super().__init__(name)

        self._NodeName = name
        self._NodeId = int(nodeid)
        self._host = host
        self._port = int(port)
        self._poll_interval = int(pollinterval)
        
        self._next_poll_time = None
        self._obd = None
        self._commands =[
            # Command specification for ODB PID 015B
            OBDCommand("EV_BATTERY_SOC", "EV Battery State of Charge", b"015B", 3, percent, ECU.ENGINE, True),
            # Command specification for ODB PID 01A6
            OBDCommand("ODOMETER", "Odometer", b"01A6", 6, uas(0x25), ECU.ENGINE, True)
        ]
        

    def close(self):
        if self._obd:
            self._log.info("Closing connection to OBD2 dongle")
            self._obd.close()
            self._obd = None
        
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
        """Read data from OBD dongle"""

        # Wait until we are ready to fetch
        if not self._is_it_time():
            return
        
        cargo = None
        
        try:
            self._connect()
    
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
        
    def _connect(self):
        # Nothing to do if already connected
        if self._obd:
            return
            
        # Create a TCP socket 
        self._log.info(f"Connecting to OBD2 dongle {self._host}:{self._port}")
        
        # fast off as it causes unreliability, protocol=6 for Velar may need changing for another vehicle
        self._obd = self.OBDPrivate(self._host, self._port, fast=False, protocol="6")
        
        if not self._obd.is_connected():
            raise Exception(f"Unable to connect to OBD dongle or car at {self._host}:{self._port}")       
            
    def _fetch(self):
        names = []
        values = []
        
        for command in self._commands:
            response = self._obd.query(command, force=True) # force to avoid checking if commands is in obd.commands
            if not response.value:
                self._log.warn(f"No value for {command.name}")
                continue
            names.append(command.name)
            value = float(response.value.magnitude)
            values.append(value)
            self._log.info(f"{command.name}: {value}")
          
        # Odometer becomes unavailable after a period of ignition off, battery SoC should be available all the time
        # so if none of the values are obtained it's an error - raise exception to trigger retry 
        if not values:
            raise Exception(f"No values obtained")
            
        # Add the user-friending SoC (i.e. that shown as 0-100% range on the dash to the user).  This is rather hacky
        # but not expecting this code to ever be shared.
        try:
            index = names.index("EV_BATTERY_SOC")
            raw_value = values[index]
            user_value = (raw_value*1.28)-20.7
            if user_value > 100:
                user_value = 100
            names.append("EV_USER_SOC")
            values.append(user_value)
            self._log.info(f"EV_USER_SOC: {user_value}")           
        except ValueError:
            pass
            
        # Cargo object for returning values
        c = Cargo.new_cargo()
        c.rawdata = None
        c.realdata = values
        c.names = names
        c.nodeid = self._NodeId
        c.nodename = self._NodeName            

        return c

           

 
