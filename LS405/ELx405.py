from pymodbus.client import ModbusSerialClient
import json
import time

class ELx405:
    def __init__(self, port, slave=1):
        self.client = ModbusSerialClient(
            port=port,
            baudrate=9600,
            parity='N',
            stopbits=1,
            bytesize=8,
            timeout=1
        )
        self.slave = slave
        self.client.connect()

    def start(self):
        self.client.write_register(0, 1, slave=self.slave)

    def status(self):
        r = self.client.read_holding_registers(9, 1, slave=self.slave)
        return r.registers[0]

    def wait_done(self):
        last = None
        while True:
            s = self.status()
            if last == 1 and s == 2:
                return
            last = s
            time.sleep(0.5)
