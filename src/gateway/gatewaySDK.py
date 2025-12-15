import paho.mqtt.client as mqtt
import json
import time
client=None
config=None
LaGaAppKey="B2DC6B3D8DCE4D8DB8A71B38D346CA97"
LaGaSecret="i4HZG0mZJMQKNWUNYDGMjj1g1gIhLrenGkHCMKLDR5w"
functionc=None
def mqttConnet(mqttConfig):
   global client,config
   config=mqttConfig
   client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,mqttConfig["clientId"],protocol=mqtt.MQTTv311)
   client.username_pw_set(mqttConfig["user"], mqttConfig["password"])
   client.connect(host=config["host"],port=config["port"],keepalive=60)
  # client.connect_callback=connectCallback
    # 保持连接
   client.subscribe(config["subTopic"])
   client.on_message=onsubscribe
   print("-------mqtt_done!!!--------")
   client.loop_forever() 
   
def connectCallback():
     global client,config
     client.subscribe(config["subTopic"])
def onsubscribe(client,userdata,msg):
     global functionc
     data=json.loads(msg.payload.decode())
     topic=msg.topic
     functionc(topic,data)
def publish(topic,msg):
     global client,config
     json_string = json.dumps(msg,  ensure_ascii=False)
     client.publish(topic,json_string)
def init(serverIP,port,topicNames,functionOnsub):
    print("-------gw init doing!---------")
    global LaGaAppKey,LaGaSecret,functionc
    config={
        "user":LaGaAppKey,
        "password":LaGaSecret,
        "host":serverIP,
        "port":port,
        "subTopic":topicNames,
        "clientId":"app_"+str(time.time())

    }
    functionc=functionOnsub
    mqttConnet(config)


if __name__ == "__main__":
    topics=["/sys/rx8HhkWQ337sCAFB/Y879/s/#"]
    init("101.52.216.165",18831,topics)