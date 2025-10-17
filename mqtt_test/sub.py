import paho.mqtt.client as mqtt

broker = "test.mosquitto.org"
port = 1883
topic = "my_topic/public"

# 接收消息回调
def on_message(client, userdata, msg):
    print(f"Received: {msg.payload.decode()} from topic {msg.topic}")

client = mqtt.Client()
client.on_connect = lambda c, u, f, rc: c.subscribe(topic)  # 连接后订阅主题
client.on_message = on_message
client.connect(broker, port, 60)
client.loop_forever()