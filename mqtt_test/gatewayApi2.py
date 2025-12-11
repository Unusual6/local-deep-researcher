import base64
import socket
import struct
import paho.mqtt.client as mqtt
import json
import hashlib
import time
import threading
UDP_IP = "127.0.0.1"  # 👈 改成运行 C# 程序的机器 IP
UDP_PORT = 1616       # 👈 改成 C# 程序监听的端口

client=None
config=None
# =============================================
# 工具函数：计算 CRC16（与 C# 的 Utility.CalculateCRC16 一致）
# =============================================
def calculate_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF  # 强制 16bit
    return crc

def send_command(command: int, data: bytes = b''):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)  # 设置超时时间，避免卡死
    # 包格式：包头(4) + 数据长度(2) + 命令(2) + 数据(N) + 校验(2)
    header = b'\x19\x81\x06\x17'
    length = len(data)
    packet_without_crc = header + struct.pack('<H', length) + struct.pack('<H', command) + data
    crc = calculate_crc16(packet_without_crc)
    packet = packet_without_crc + struct.pack('<H', crc)

    print(f"[发送] 命令: 0x{command:04X}, 数据: {data}")
    sock.sendto(packet, (UDP_IP, UDP_PORT))

    try:
        response, addr = sock.recvfrom(4096)
        print(f"[接收] 来自 {addr} 的响应: {response}")

        # 假设响应格式一致，尝试提取数据部分（跳过包头4 + 长度2 + 命令2，剩下的是数据，最后2字节是CRC）
        if len(response) >= 10:
            data_part = response[8:-2]  # 去掉包头4 + 长度2 + 命令2 + 数据N + 去掉最后2字节校验
            try:
                text = data_part.decode('gbk')  # 设备返回的文本通常是 GBK 编码
                print(f"[解析] 响应内容（GBK解码）: {text}")
                return text,response
            except UnicodeDecodeError:
                print(f"[解析] 响应是二进制或非文本，原始字节: {data_part}")
                return data_part
        else:
            print("[解析] 响应格式不符合预期，长度不足")
            return None
    except Exception as e:
        print(f"[错误] 发送命令时发生异常: {type(e).__name__}: {e}")
        return "",""
    finally:
        sock.close()

def mqttConnet(mqttConfig):
   global client,config
   config=mqttConfig
   client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,mqttConfig["clientId"],protocol=mqtt.MQTTv311)
   client.username_pw_set(mqttConfig["user"], mqttConfig["password"])
   client.connect(host=config["host"],port=config["port"],keepalive=60)
    # 保持连接
   client.subscribe(config["subTopic"])
   client.on_message=onsubscribe
   client.loop_forever()

def publish(msg):
     global client,config
     json_string = json.dumps(msg,  ensure_ascii=False)
     client.publish(config["publish"],json_string)

def sendGetList():
    result=send_command(0x0001,b"")
    return result

def onsubscribe(client,userdata,msg):
     data=json.loads(msg.payload.decode())
     topic=msg.topic

     print(topic+":"+json.dumps(data))
     #服务事件
     if "/service/" in topic:
         id = data["id"]
         if topic.endswith("/start"):
            text,result=send_command(0x0102,b"")
            serviceRely(id,"start",text)
         if topic.endswith("stop"):
            text,result=send_command(0x0108,b"")
            serviceRely(id,"stop",text)
         if topic.endswith("/getlist"):
            print(msg)
            id=data["id"]
            text,result=sendGetList()
            serviceRely(id,'getlist',text)
         if topic.endswith("/select_exe"):
             exe_name=data["params"]["exe"]
             print(exe_name)
             text,result=send_command(0x0101,exe_name.encode('gbk'))
             print(text,result[8])
             if result[8]==0:
                 text="成功"
             elif result[8]==1:
                 text="失败"
             elif result[8]==2:
                 text="程序不存在"
             serviceRely(id,'select_exe',text)
         if topic.endswith("/get_log"):
             text,result=send_command(0x1000,b"")
             serviceRely(id,'get_log',text)
         if topic.endswith("/check_status"):
             result=send_command(0x0002,b"")
             print(result[0])
             if result[0]==255:
                 status = "停止"
             elif result[0]==0:
                 status="未启动"
             elif result[0]==2:
                 status="运行中"

             serviceRely(id,'check_status',result[0])
         if topic.endswith("/set_position"):
            position=int(data["params"]["position"])
            position = position.to_bytes(4, byteorder='little')
            text, result = send_command(0x0105,position)
            serviceRely(id, "reset_arm", text)
         if topic.endswith("/reset_arm"):
             text,result=send_command(0x0108,b"")
             serviceRely(id,"reset_arm",text)
         if topic.endswith("/set_var"):
             var_name=int(data["params"]["var_name"])
             var_value=int(data["params"]["var_value"])
             variable_line = f"{var_name}\r\n{var_value}"
             variable_bytes = variable_line.encode('gbk')
             base64_str = base64.b64encode(variable_bytes).decode('ascii')
             final_data_bytes = base64_str.encode('gbk')
             text, result = send_command(0x0107,final_data_bytes)
             serviceRely(id, "set_var", text)
         if topic.endswith("/box_change"):
             text,result=send_command(0x0106,b"")
             serviceRely(id, "box_change",text)
         if topic.endswith("/pause"):
             text,result=send_command(0x0104,data=bytes([0]))
             serviceRely(id, "pause", text)
         if topic.endswith("/continue"):
             text,result=send_command(0x0104,data=bytes([1]))
             serviceRely(id, "continue", text)

def publishRely(publicType,serviceName,msg):
     global client,config
     topic=config["relyBase"]+publicType+"/"+serviceName
     json_string = json.dumps(msg,  ensure_ascii=False)
     client.publish(topic,json_string)

def propertyPublish(msg):
     global client,config
     topic=config["relyBase"]+"event/property/post"
     payload={
         "id":config["user"]+"_"+ str(int(time.time())),
         "method":"thing.event.property.post",
         "params":msg,
         "version":"1.0.0"
     }
     json_string = json.dumps(msg,  ensure_ascii=False)
     client.publish(topic,json_string)

def serviceRely(id,serviceName, msg):
    global client, config
    topic = config["relyBase"] + "service/" + serviceName + "_reply"
    payload = {
        "id": id,
        "method": "thing.service." + serviceName + "_reply",
        "params": {"params": msg},
        "version": "1.0.0",
        "code":0
    }
    json_string = json.dumps(payload, ensure_ascii=False)

    client.publish(topic, json_string)

    print(json_string)

def md5Encode(key):
    text_bytes = key.encode("utf-8")
    md5_obj = hashlib.md5(text_bytes)
    # 3. 获取32位小写十六进制结果（hexdigest()默认返回小写32位）
    return md5_obj.hexdigest()

if __name__ == "__main__":
    productKey="rx8HhkWQ337sCAFB"
    productSecret="972c4e48f27d4ef1938c80dc28a6c232"

    devCode="Y879"
    devNum="m1"
    clientId=productKey+"_"+devCode+"_"+devNum
    subTopic="/sys/"+productKey+"/"+devCode+"/c/#"
    config={
      "clientId":clientId,
      "user":devCode,
      "host":"101.52.216.165",
      "port":18831,
      "password":md5Encode(productSecret+clientId),
      "subTopic":subTopic,
      "relyBase":"/sys/"+productKey+"/"+devCode+"/s/"
    }
    print(config)
    mqttConnet(config)
    sing_thread = threading.Thread(target=mqttConnet, args=(config,))
    sing_thread.start()
    #status={"status":2}
    #propertyPublish(status)