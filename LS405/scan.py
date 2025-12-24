import json
import time
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient(
    port="COM3",
    baudrate=9600,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)

assert client.connect(), "串口连接失败"

SLAVE_ID = 1
result = {}

for addr in range(0, 100):
    resp = client.read_holding_registers(addr, 1, slave=SLAVE_ID)
    if resp and not resp.isError():
        result[f"400{addr+1:04d}"] = resp.registers[0]
    time.sleep(0.05)

client.close()

with open("dump.json", "w") as f:
    json.dump(result, f, indent=2)
