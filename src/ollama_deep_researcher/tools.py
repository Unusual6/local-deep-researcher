"""
LangGraph Agent for Automated ELISA Experiment Orchestration
Author: jpf
"""

import json
import time
import paho.mqtt.client as mqtt
from typing import Dict, Any, List
from langchain.tools import Tool, tool
from langchain_openai import ChatOpenAI


##############################################
# 工具统一注册函数
##############################################
def get_tools(llm):
    """
    构造实验调度需要的四个工具：
    1. 解析实验需求
    2. 生成XDL协议
    3. 查询Edge Server状态（MQTT）
    4. 下发任务与监控反馈（MQTT）
    返回 Tool 列表，可直接用于 LangGraph Agent
    """
    # llm = ChatOpenAI(model="gpt-4o-mini")

    ##############################################
    # 1️⃣ 解析实验需求
    ##############################################
    def parse_experiment_description(user_input: str) -> Dict[str, Any]:
        """
        解析自然语言实验需求，输出结构化实验信息。
        """
        prompt = f"""
        你是实验调度助手，请从以下描述中提取实验信息：
        - 实验类型(type)
        - 目标物(target)
        - 样品编号(sample_id)
        - 任何其他参数(parameters)
        输出为JSON。
        用户输入: {user_input}
        """
        response = llm.predict(prompt)
        try:
            return json.loads(response)
        except Exception:
            return {"type": "ELISA", "target": "IFN-γ", "sample_id": "unknown"}

    tool_parse = Tool(
        name="parse_experiment_description_tool",
        description="解析自然语言实验需求，输出结构化实验信息。",
        func=parse_experiment_description
    )

    ##############################################
    # 2️⃣ 生成XDL协议描述
    ##############################################
    def generate_xdl_protocol(exp_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据实验类型生成XDL协议模板。
        """
        protocol_templates = {
            "ELISA": """<?xdl version="1.0.0" ?>
<XDL>
  <Synthesis>
    <Hardware>
      <Component id="washer" type="plate_washer" />
      <Component id="reader" type="plate_reader" />
    </Hardware>
    <Reagents>
      <Reagent name="PBST" id="PBST" />
      <Reagent name="TMB" id="TMB" />
      <Reagent name="Stop" id="Stop" />
    </Reagents>
    <Procedure>
      <Add reagent="PBST" vessel="plate" volume="100 uL" />
      <Wait time="5 min" />
      <Add reagent="TMB" vessel="plate" volume="50 uL" />
      <Add reagent="Stop" vessel="plate" volume="50 uL" />
      <Read vessel="plate" wavelength="450 nm" />
    </Procedure>
  </Synthesis>
</XDL>"""
        }
        xdl = protocol_templates.get(exp_info.get("type", "ELISA"), "")
        return {
            "protocol_type": exp_info.get("type", "ELISA"),
            "xdl": xdl,
            "params": exp_info
        }

    tool_xdl = Tool(
        name="generate_xdl_protocol_tool",
        description="根据实验类型生成XDL实验协议（XDL格式字符串）。",
        func=generate_xdl_protocol
    )

    ##############################################
    # 3️⃣ 查询Edge Server状态（通过MQTT）
    ##############################################
    def query_edge_server(protocol_type: str) -> Dict[str, Any]:
        """
        查询可执行指定协议的Edge Server。
        """
        broker = "mqtt.lab.local"
        topic = "/lab/registry/status"
        edges = []

        def on_message(client, userdata, msg):
            payload = json.loads(msg.payload.decode())
            if (
                payload.get("status") == "idle"
                and protocol_type in payload.get("supported_protocols", [])
            ):
                edges.append(payload)

        client = mqtt.Client()
        client.on_message = on_message
        client.connect(broker, 1883, 60)
        client.subscribe(topic)
        client.loop_start()
        time.sleep(2)
        client.loop_stop()
        client.disconnect()

        if not edges:
            return {"available_edges": [], "message": "No idle edge server available"}
        return {"available_edges": edges}

    tool_query = Tool(
        name="query_edge_server_tool",
        description="通过MQTT查询空闲Edge Server节点及其支持协议。",
        func=query_edge_server
    )

    ##############################################
    # 4️⃣ 调度执行与反馈监控（通过MQTT）
    ##############################################
    def dispatch_and_monitor(edge_info: Dict[str, Any], protocol_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        向指定Edge下发实验指令并监听执行状态。
        """
        broker = "mqtt.lab.local"
        edge_id = edge_info.get("id", "edge01")
        control_topic = f"/lab/{edge_id}/control"
        feedback_topic = f"/lab/{edge_id}/feedback"

        result = {"status": "pending", "feedback": []}

        def on_message(client, userdata, msg):
            payload = json.loads(msg.payload.decode())
            result["feedback"].append(payload)
            if payload.get("status") == "completed":
                result["status"] = "done"

        client = mqtt.Client()
        client.on_message = on_message
        client.connect(broker, 1883, 60)
        client.subscribe(feedback_topic)
        client.loop_start()

        # 发布实验任务
        payload = {
            "cmd": "run_protocol",
            "protocol": protocol_data["protocol_type"],
            "xdl": protocol_data["xdl"],
            "params": protocol_data["params"]
        }
        client.publish(control_topic, json.dumps(payload))

        timeout = time.time() + 300
        while result["status"] == "pending" and time.time() < timeout:
            time.sleep(2)

        client.loop_stop()
        client.disconnect()
        return result

    tool_dispatch = Tool(
        name="dispatch_and_monitor_tool",
        description="通过MQTT下发实验执行命令并实时监控反馈。",
        func=dispatch_and_monitor
    )

    ##############################################
    # 汇总所有工具
    ##############################################
    return [tool_parse, tool_xdl, tool_query, tool_dispatch]


##############################################
# 主执行测试
##############################################
if __name__ == "__main__":

    tools = get_tools()
    print(f"✅ 已加载工具 {len(tools)} 个：")
    for t in tools:
        print(f" - {t.name}: {t.description}")

    # 测试运行一个简单流程
    exp = tools[0].func("帮我检测样品S123的IFN-γ浓度")
    proto = tools[1].func(exp)
    print("\n🧪 生成的XDL片段：")
    print(proto["xdl"][:300], "...")
