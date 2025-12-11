import paho.mqtt.client as mqtt
# import threading,pyautogui
import time
# from control_sfw import open_software, fill_command_field

BROKER = "101.52.216.165"  # 改成公网 IP
PORT = 18830
TOPIC = "chat/channel1"
CLIENT_ID = "ClientA"

def on_connect(client, userdata, flags, rc):
    print(f"[{CLIENT_ID}] 已连接，结果码: {rc}")
    client.subscribe(TOPIC)
    
def on_message(client, userdata, msg):
    message = msg.payload.decode().strip().lower()
    print(f"📩 收到消息：{message}")

    if "doing" in message:  # ✅ 模糊匹配
        print("⚙️ 检测到控制指令 'doing'")
        # open_software()
        # fill_command_field("start_device")
        # pyautogui.press('enter')
        client.disconnect()



def sender_loop(client):
    while True:
        msg = input("你说: ")
        if msg.lower() in ["exit", "quit"]:
            break
        client.publish(TOPIC, f"{CLIENT_ID}: {msg}")

from paho.mqtt.client import CallbackAPIVersion
client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_start()

sender_loop(client)
client.loop_stop()
client.disconnect()
