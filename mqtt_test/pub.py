import paho.mqtt.client as mqtt

# MQTT服务器地址和端口
broker = "test.mosquitto.org"
port = 1883
topic = "my_topic/public"

# 连接回调
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # 发布消息
    client.publish(topic, "Hello from PC1 (Code)")

client = mqtt.Client()
client.on_connect = on_connect
client.connect(broker, port, 60)  # 60为keepalive时间
client.loop_forever()  # 保持连接并处理消息