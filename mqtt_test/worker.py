import json
import re
from test2 import *
import paho.mqtt.client as mqtt

# === 配置 ===
BROKER = "101.52.216.165"  # 你的 EMQX 地址
PORT = 1883
REQUEST_TOPIC = "request/topic"
RESPONSE_TOPIC = "response/topic"


# === MQTT 回调函数 ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[Subscriber] ✅ 已连接到 MQTT Broker!")
        # 订阅请求主题，准备接收请求
        client.subscribe(REQUEST_TOPIC)
        print(f"[Subscriber] 👂 已订阅请求主题: {REQUEST_TOPIC}")
    else:
        print(f"[Subscriber] ❌ 连接失败，错误码: {rc}")


def on_message(client, userdata, msg):
    print(f"[Subscriber] 📥 收到请求 [主题: {msg.topic}]: {msg.payload.decode()}")
    msg = msg.payload.decode()
    msg = json.loads(msg)
    command=msg['command']
#获取脚本
    if command == "0x00,0x01":
        text,response1=send_command(0x0001)

        try:
            recipes = re.findall(r'\{([^}]*)\}', text)
            list_data = str(recipes)
            response = f"{{\n  \"list_data\": \"{list_data}\"\n}}"
            client.publish(RESPONSE_TOPIC, response)
        except:
            response = f"{{\n  \"list_data\": \"null\"\n}}"
            client.publish(RESPONSE_TOPIC, response)
#选择脚本
    elif command == "0x01,0x01":
        exe = msg['exe']
        print(exe)
        text,response=send_command(0x0101, exe.encode('gbk'))
        print(response[8])
        if response[8]:
            if response[8] == 0:
                result="选择成功"
                client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"{result}\"\n}}")
            elif response[8] == 1:
                result="有程序运行无法切换"
                client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"{result}\"\n}}")
            elif response[8] == 2:
                result='程序名未找到'
                client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"{result}\"\n}}")
#启动脚本
    elif command == "0x01,0x02":
        text,result=send_command(0x0102)
        if result == ""or result is None:
            pass
        else:
            response = f"{{\n  \"result\": \"{text}\"\n}}"
            client.publish(RESPONSE_TOPIC, response)
#查询运行状态
    elif command == "0x00,0x02":
        result=send_command(0x0002)
        if result[0] == 255:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"无选中程序\"\n}")
        elif result[0] == 0:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"空闲\"\n}")
        elif result[0] == 1:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"运行中\"\n}")
        elif result[0] == 2:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"暂停\"\n}")
        elif result[0] == 254:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"未知错误\"\n}")
    elif command == "0x01,0x03":
        text,result=send_command(0x0103)
        if result == ""or result is None:
            pass
        else:
            response = f"{{\n  \"result\": \"{text}\"\n}}"
            client.publish(RESPONSE_TOPIC, response)
#暂停或者恢复运行
    elif command == "0x01,0x04":
        if msg["is_pause"] == "0":
            text,result=send_command(0x0104, data=bytes([0]))
            if result == "" or result is None:
                client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"暂停成功\"\n}")
            else:
                client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"{text}\"\n}}")
        elif msg["is_pause"] == "1":
            text,result=send_command(0x0104, data=bytes([1]))
            if result == "" or result is None:
                client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"恢复成功\"\n}")
            else:
                client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"{text}\"\n}}")
        else:
            response = f"{{\n  \"result\": \"未知错误\"\n}}"
            client.publish(RESPONSE_TOPIC, response)
#设置枪头位置
    elif command == "0x01,0x05":
        position = int( msg["position"])

        position = position.to_bytes(4, byteorder='little')

        text,result=send_command(0x0105, position)

        response =  f"{{\n  \"result\": \"{text}\"\n}}"
        client.publish(RESPONSE_TOPIC, response)
#更换枪头盒确认
    elif command == "0x01,0x06":
        text,result=send_command(0x0106)
        if result == "" or result is None:
            client.publish(RESPONSE_TOPIC, "{\n  \"result\": \"error\"\n}")
        else:
            client.publish(RESPONSE_TOPIC, f"{{\n  \"result\": \"null\"\n}}")
#设置变量参数
    elif command == "0x01,0x07":
        var_name=msg["var_name"]
        var_value=msg["var_value"]
        variable_line = f"{var_name}\r\n{var_value}"
        variable_bytes = variable_line.encode('gbk')
        base64_str = base64.b64encode(variable_bytes).decode('ascii')
        final_data_bytes = base64_str.encode('gbk')
        text,result=send_command(0x0107, final_data_bytes)
        response =  f"{{\n  \"result\": \"{text}\"\n}}"
        client.publish(RESPONSE_TOPIC, response)
#机械臂移动到原点
    elif command == "0x01,0x08":
        text,result=send_command(0x0108)
        response =  f"{{\n  \"result\": \"{text}\"\n}}"
        client.publish(RESPONSE_TOPIC, response)
#查看日志
    elif command == "0x10,0x00":
        text,result=send_command(0x1000)
        response =  f"{{\n  \"result\": \"{text}\"\n}}"
        client.publish(RESPONSE_TOPIC, response)


# === 启动 MQTT 客户端 ===
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message


print("[Subscriber] 🔌 正在连接 MQTT Broker...")
client.connect(BROKER, PORT, 60)

# 开始循环处理消息
client.loop_forever()