#!/usr/bin/python3
# EmonHubModbusTcpInterfacer2 released for use by OpenEnergyMonitor project
# GNU GENERAL PUBLIC LICENSE -  Version 2, June 1991
# See LICENCE and README file for details

__author__ = 'Dan Conlon'

import sys
import time
import traceback
import Cargo
from pymodbus.client import ModbusTcpClient
from emonhub_interfacer import EmonHubInterfacer


class EmonHubModbusTcpInterfacer2(EmonHubInterfacer):

    def __init__(self, name, host, port=502, pollinterval=60, nodeid=68):
        """Initialize interfacer"""

        # Initialization
        super().__init__(name)

        self._NodeName = name
        self._NodeId = int(nodeid)
        self._host = host
        self._port = int(port)
        self._poll_interval = int(pollinterval)
        
        self._next_poll_time = None
        self._modbus = None
        
        self._slaves = []
        
        
    def set(self, **kwargs):
        self._slaves = kwargs['slaves']
        super().set(**kwargs)

    def close(self):
        if self._modbus:
            self._log.info("Closing connection")
            self._modbus.close()
            self._modbus = None
        
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
        if self._modbus:
            return
        
        # Connect to Modbus gateway
        self._modbus = ModbusTcpClient(self._host, port=self._port)        
            
    def _fetch(self):
        data = {}
        
        for name, config in self._slaves.items():
            slave_id = int(config['slave_id'])
    
            # Read coils
            if 'coil_names' in config:
                address = config['coil_address'] if 'coil_address' in config else 0
                data = data | self._read_bits('read_coils', slave_id, address, [name + "_" + n for n in  config['coil_names']])
            
            # Read discrete inputs
            if 'discrete_input_names' in config:
                address = config['discrete_input_address'] if 'discrete_input_address' in config else 0
                data = data | self._read_bits('read_discrete_inputs', slave_id, address, [name + "_" + n for n in  config['discrete_input_names']])
            
            # Read input registers
            if 'input_register_names' in config:
                names = [name + "_" + n for n in config['input_register_names']]
                address = config['input_register_address'] if 'input_register_address' in config else 0
                scales = [float(n) for n in config['input_register_scales']] if 'input_register_scales' in config else [1] * len(names)
                data = data | self._read_registers('read_input_registers', slave_id, address, names, scales)
        
            # Read holding registers
            if 'holding_register_names' in config:
                names = [name + "_" + n for n in config['holding_register_names']]
                address = config['holding_register_address'] if 'holding_register_address' in config else 0
                scales = [float(n) for n in config['holding_register_scales']] if 'holding_register_scales' in config else [1] * len(names)
                data = data | self._read_registers('read_holding_registers', slave_id, address, names, scales)                
        
        # Log the data
        for key, value in data.items():
            self._log.debug("%s - %s", key, value)
        
        # Cargo object for returning values
        c = Cargo.new_cargo()
        c.rawdata = None
        c.realdata = data.values()
        c.names = data.keys()
        c.nodeid = self._NodeId
        c.nodename = self._NodeName            

        return c
        
    def _read_bits(self, method, slave_id, start_address, names):
        result = {}
    
        # Read len(names) of consecutive coils/registers
        res = getattr(self._modbus,method)(start_address, count = len(names), slave=slave_id)
        if not res.function_code < 0x80:
            self._log.error(f"{method} failed")
            return result
    
        for idx, name in enumerate(names):
            result[name] = 1 if res.bits[idx] else 0
        
        return result
    
    def _read_registers(self, method, slave_id, start_address, names, scales):
        result = {}
    
        # Read len(names) of consecutive coils/registers
        res = getattr(self._modbus,method)(start_address, count = len(names), slave=slave_id)
        if not res.function_code < 0x80:
            self._log.error(f"{method} failed")
            return result
                
        for idx, name in enumerate(names):
            result[name] = res.registers[idx] * scales[idx]
        
        return result   

           

 
