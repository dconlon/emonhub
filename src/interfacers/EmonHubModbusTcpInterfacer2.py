#!/usr/bin/python3
# EmonHubModbusTcpInterfacer2 released for use by OpenEnergyMonitor project
# GNU GENERAL PUBLIC LICENSE -  Version 2, June 1991
# See LICENCE and README file for details

__author__ = 'Dan Conlon'

import sys
import time
import traceback
import Cargo
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

        # Only load pymodbus and packaging modules during init so that emonhub without this interfacer defined in its
        # configuration will still start without pymodbus and packaging installed
        import pymodbus
        from packaging.version import parse as parse_version
        if parse_version(pymodbus.__version__) < parse_version('3.10.0'): # Tested up to v3.11.2
            raise Exception(f"pymodbus version {pymodbus.__version__} found, minimum version 3.10.0 required")
        self.pymodbus = pymodbus.client.ModbusTcpClient

        self._DATATYPES = {
            'float32': (2, self.pymodbus.DATATYPE.FLOAT32),
            'float64': (4, self.pymodbus.DATATYPE.FLOAT64),
            'int16': (1, self.pymodbus.DATATYPE.INT16),
            'int32': (1, self.pymodbus.DATATYPE.INT32),
            'int64': (1, self.pymodbus.DATATYPE.INT64),
            'uint16': (1, self.pymodbus.DATATYPE.UINT16),
            'uint32': (1, self.pymodbus.DATATYPE.UINT32),
            'uint64': (1, self.pymodbus.DATATYPE.UINT64)
        }
        
        
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
        self._modbus = self.pymodbus(self._host, port=self._port)        
            
    def _fetch(self):
        data = {}
        
        for name, config in self._slaves.items():
            slave_id = int(config['slave_id'])
    
            # Read coils
            if 'coil_names' in config:
                addresses = config['coil_addresses'] if 'coil_addresses' in config else [0]
                data = data | self._read_bits('read_coils', slave_id, addresses, [name + "_" + n for n in  config['coil_names']])
            
            # Read discrete inputs
            if 'discrete_input_names' in config:
                addresses = config['discrete_input_addresses'] if 'discrete_input_addresses' in config else [0]
                data = data | self._read_bits('read_discrete_inputs', slave_id, addresses, [name + "_" + n for n in  config['discrete_input_names']])
            
            # Read input registers
            if 'input_register_names' in config:
                names = [name + "_" + n for n in config['input_register_names']]
                addresses = [int(a) for a in config['input_register_addresses']] if 'input_register_addresses' in config else [0]
                datatypes = config['input_register_datatypes'] if 'input_register_datatypes' in config else None
                scales = [float(n) for n in config['input_register_scales']] if 'input_register_scales' in config else [1] * len(names)
                data = data | self._read_registers('read_input_registers', slave_id, addresses, datatypes, names, scales)
        
            # Read holding registers
            if 'holding_register_names' in config:
                names = [name + "_" + n for n in config['holding_register_names']]
                addresses = [int(a) for a in config['holding_register_addresses']] if 'holding_register_addresses' in config else [0]
                datatypes = config['holding_register_datatypes'] if 'holding_register_datatypes' in config else None
                scales = [float(n) for n in config['holding_register_scales']] if 'holding_register_scales' in config else [1] * len(names)
                data = data | self._read_registers('read_holding_registers', slave_id, addresses, datatypes, names, scales)                
        
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
        
    def _read_bits(self, method, slave_id, addresses, names):
        result = {}

        if len(addresses) == 1:
            # Just given a starting addresses, all are consecutive
            addresses = list(range(addresses[0],addresses[0]+len(names)))
        elif len(addresses) != len(names):
            self._log.error(f"{method} addresses and names must have equal number of parameters")
            return {}

        # Read len(addresses) of consecutive coils/discrete inputs
        res = getattr(self._modbus,method)(addresses[0], count = len(addresses), device_id=slave_id)
        if not res.function_code < 0x80:
            self._log.error(f"{method} failed")
            return result

        # Transform to name/value pairs
        result = {}
        for idx, name in enumerate(names):
            result[name] = 1 if res.bits[idx] else 0
        
        return result
    
    def _read_registers(self, method, slave_id, addresses, datatypes, names, scales):
        if len(addresses) == 1:
            # Just given a starting addresses, all are consecutive
            addresses = list(range(addresses[0],addresses[0]+len(names)))
        elif len(addresses) != len(names):
            self._log.error(f"{method} addresses and names must have equal number of parameters")
            return {}

        # If given datatypes, some are multi-register, expand the list of addresses
        expanded_addresses = []
        if datatypes:
            for (start_address, datatype) in zip(addresses, datatypes):
                no_registers = self._DATATYPES[datatype][0]
                expanded_addresses.extend(range(start_address,start_address+no_registers))
        else:
            expanded_addresses = addresses

        # Request up to 40 registers at a time (TODO: miss out non-consecutive addresses)
        registers = []
        start_address = expanded_addresses[0]
        while True:
            address_count = min(40, expanded_addresses[-1]-start_address+1)
            resp = getattr(self._modbus,method)(start_address, count = address_count, device_id=slave_id)
            if not resp.function_code < 0x80:
                self._log.error(f"{method} failed")
                return {}
            registers.extend(resp.registers)
            start_address += 40
            if start_address > expanded_addresses[-1]:
                break

        # Get the registers required, where neccessary converting the datatype from multiple registers
        values = []
        for idx, start_address in enumerate(addresses):
            start_address -= addresses[0] # adjust start_address for where we started reading registers
            value = registers[start_address]
            if datatypes:
                (no_registers_for_type, pymodbus_type) = self._DATATYPES[datatype]
                registers_for_value = registers[start_address:start_address+no_registers_for_type]
                value = self._modbus.convert_from_registers(registers = registers_for_value, data_type = pymodbus_type)
            values.append(value)

        # Transform to name/value pairs and apply scaling factor
        result = {}       
        for idx, name in enumerate(names):
            result[name] = values[idx] * scales[idx]
        return result   

           

 
