import src.gateway.gatewaySDK as gatewaySDK
import time 
import threading
from flask import Flask,request
from .zuofei_tools import extract_params_to_dict,program_manager
Online=False
app = Flask(__name__)
app.debug = False
config={ 
    "productKey":"rx8HhkWQ337sCAFB",
     "devCode":"Y879",
     "serverIp":"101.52.216.165",
    #"serverIp":"127.0.0.1",
     "port":18831
    }
def init():
   print("-------ws init doing!---------")
   global config
   devtopic="/sys/"+config["productKey"]+"/"+config["devCode"]+"/s/#"
   topicNames=devtopic
   gatewaySDK.init(config["serverIp"],config["port"],topicNames,onsub)
def cmdInfo(cmd,data):
   if cmd=="connect":
      getOnline()
   if cmd=="start":
      sendService("start",None,None)
   if cmd=="stop":
      sendService("stop",None,None)
   if cmd=="getlist":
     sendService("getlist",None,None)
   if cmd=="select_exe":
      sendService("select_exe","exe",data)
def getOnline():
    baseTopic="/sys/"+config["productKey"]+"/"+config["devCode"]
    serviceMethod="thing.service.property.get"
    topicName=baseTopic+"/o/service/property/get"
    payload={
         "id":"dev_"+str(time.time()),
         "method":serviceMethod,
         "params":{}
      }
    gatewaySDK.publish(topicName,payload) 
def sendService(serviceName,key,data):
    global Online
    if Online ==False:
       logInfo("设备离线，无法控制")
       return None
    baseTopic="/sys/"+config["productKey"]+"/"+config["devCode"]
    serviceMethod="thing.service."
    topicName=baseTopic+"/c/service/"+serviceName
    params={}
    if(data!=None):
       params={key:data}
    payload={
         "id":"dev_"+str(time.time()),
         "method":serviceMethod+serviceName,
         "params":params
      }
    gatewaySDK.publish(topicName,payload) 
def logInfo(msg):
    print("消息:"+msg)
def onsub(topicName,data):
   global Online
   topics= topicName.split("/")
   if len(topics)<=6:
      logInfo("设备异常回复")
   cmd=topics[5]
   serverName=topics[6].replace("_reply","")
   if cmd=="service":#服务回复
      if(serverName=="start"):
         logInfo("启动成功")
      if serverName=="stop":
         logInfo("停止成功")
      if serverName=="getlist":
         logInfo("获取脚本成功")
         print(data["params"]["params"])
         program_list = extract_params_to_dict(data["params"]["params"])
         program_manager.program_list = program_list
         logInfo(f"[a.py回调] 程序列表更新：{program_manager.program_list} 时间：{time.time()}")
   if cmd=="event":
      if(serverName=="online"):
         online=data["params"]["online"]
         if(online==1):
            Online=True
            logInfo("设备在线")
         if(online==0):
            Online=False
            logInfo("设备离线")
@app.route('/test',methods=['POST'])
def test():
    json_data = request.get_json(silent=True)
    cmd=json_data["cmd"]
    data=json_data["data"]
    cmdInfo(cmd,data)
    return 'ok'
if __name__ == "__main__":
   sing_thread = threading.Thread(target=init)
   sing_thread.start()
   app.run(debug=True)

      