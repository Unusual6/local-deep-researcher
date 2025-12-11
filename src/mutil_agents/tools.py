
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from time import sleep
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

# server config
BROKER = "127.0.0.1"  # 改成公网 IP
PORT = 18830
TOPIC = "chat/channel1"
CLIENT_ID = "ClientA"

def on_connect(client, userdata, flags, rc , TOPIC):
    print(f"[{CLIENT_ID}] 已连接，结果码: {rc}")
    client.subscribe(TOPIC)
    
def on_message(client, userdata, msg):
    message = msg.payload.decode().strip().lower()
    print(f"📩 收到消息：{message}")

# mqtt tools
def get_url_from_SuperSet():
    return "data.jpg"

@tool
def mqtt_connect_check_lab(CLIENT_ID: str, TOPIC:str):
    """实验前的设备检查，是否在线"""
    client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60 , TOPIC)
    client.loop_start()

@tool
def mqtt_done_back(reagent: str):
    """实验动作完成，mqtt返回完成消息提示"""
    print("=="*20+"all action have done!")
    url = get_url_from_SuperSet()

    return url

# cytokine_tools
@tool
def mix_reagent(reagent: str):
    """模拟工具：混合试剂"""
    print("=="*20,"tool cytokine_tools 1")
    return f"[TOOL] Mixed reagent: {reagent}"

@tool
def incubate(time_min: int):
    """模拟工具：孵育"""
    print("=="*20,"tool cytokine_tools 2")
    return f"[TOOL] Incubated for {time_min} minutes"

@tool
def measure_signal(sample: str):
    """模拟工具：测量信号"""
    print("=="*20,"tool cytokine_tools 3")
    return f"[TOOL] Signal measured for sample {sample}"

cytokine_tools = [mix_reagent, incubate, measure_signal]
cytokine_tool_node = ToolNode(cytokine_tools)

# elisa_tools
@tool
def filter_reagent(reagent: str):
    """模拟工具：过滤试剂"""
    print("=="*20+"tool elisa_tools 1")
    sleep(10)
    return f"[TOOL] Mixed reagent: {reagent}"

@tool
def shaking(time_min: int):
    """模拟工具：振荡试剂"""
    print("=="*25+"tool elisa_tools 2")
    sleep(15)
    return f"[TOOL] Incubated for {time_min} minutes"

@tool
def detect_rate(sample: str):
    """模拟工具：测定试剂的速率"""
    print("=="*30+"tool elisa_tools 3")
    sleep(20)
    return f"[TOOL] Signal measured for sample {sample}"

elisa_tools = [filter_reagent, shaking, detect_rate]
elisa_tool_nodes = ToolNode(elisa_tools)


#zuofei_tools
@tool
def connect_server():
    """
    connecting server through mqtt to experiment
    """
    sleep(5)
    print("===========1 connect_server done!===========")
    return "===========1 connect_server done!==========="

@tool
def get_program():
    """get all program list from device"""
    sleep(5)
    print("===========2 get_program done!===========")
    return "===========2 get_program done!==========="

@tool
def get_running_log():
    """get log of device """
    sleep(5)
    print("===========4 get_running_log done!===========")
    return "===========4 get_running_log done!==========="

@tool    
def run_select_program():
    """select one program in list to run"""
    sleep(5)
    # interrupt()
    print("===========3 run_select_program done!===========")
    return "===========3 run_select_program done!==========="

zuofei_tools = [run_select_program,get_program,connect_server,get_running_log]
zuofei_tools_nodes = ToolNode(zuofei_tools)

if __name__ == "__main__":
    mqtt_connect_check_lab(CLIENT_ID,TOPIC)
