from typing import Literal,Dict, Any, List
from langchain_core.tools import tool
import json , os ,re
from langchain_openai import ChatOpenAI
import json
import time
import paho.mqtt.client as mqtt
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
import logging
from pydantic import Field

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# 检测样品S3的白蛋白浓度,输出xdl.只解析实验需求，输出结果
# 合成磷酸铁锂的实验，输出xdl,先解析实验需求
# 合成氧化锆，输出xdl，仅允许使用Add步骤
# 查询可执行指定Add_Protocol的空闲 Edge Server
# 计算421*822
# 你会干什么
# langgraph Studio
# 移动液体p200加样器从试剂瓶A中吸取100uL液体到96孔板的A1孔中，生成xdl

def init_global_llm():
    """初始化全局 LLM 实例（从环境变量读取配置，避免硬编码）"""
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "GPT-oss-20b"),
        api_key=os.getenv("LLM_API_KEY", "1756891290237NvNud1IzoEnGtlNncoB1uWl"),
        openai_api_base=os.getenv("LLM_API_BASE", "http://120.204.73.73:8033/api/ai-gateway/v1"),
        temperature=0.1
    )

# 全局 LLM 实例（模块加载时自动初始化）
llm = init_global_llm()

@tool
def llm_calculator_tool(
    operation: Literal["add", "subtract", "multiply", "divide"],
    num1: float,
    num2: float,
):
    """A simple calculator tool"""
    if operation == 'add':
        result = num1 + num2
    elif operation == 'subtract':
        result = num1 - num2
    elif operation == 'multiply':
        result = num1 * num2
    elif operation == 'divide':
        if num2 == 0:
            return {"error": "Division by zero is not allowed"}
        result = num1 / num2
    else:
        return {"error": "Invalid operation"}

    return {
        "operation": operation,
        "num1": num1,
        "num2": num2,
        "result": result
    }


@tool
def weather_tool(location: str) -> str:
    """A simple weather tool that returns a mock weather report for a given location."""
    # In a real implementation, this would call a weather API.
    return f"The current weather in {location} is sunny with a temperature of 25°C."


# XDL基础骨架模板
XDL_SKELETON = """<?xdl version="1.0.0" ?>
<XDL>
  <Synthesis>
    <Hardware>
      {{hardware}}
    </Hardware>
    <Reagents>
      {{reagents}}
    </Reagents>
    <Procedure>
      {{procedure}}
    </Procedure>
    <Metadata>
      {{metadata}}
    </Metadata>
  </Synthesis>
</XDL>"""

# 优化后的LLM提示词（强制纯JSON输出，增加格式约束）
LLM_PROMPT_TEMPLATE = """
你的回复必须严格是一个 JSON 对象，不允许出现任何前缀文字、注释、解释。
你是专业生物实验工程师，仅根据以下信息生成{exp_type}实验的硬件、试剂、步骤，
严格按照指定XML格式输出，不要任何额外文字、注释、换行！

实验信息：
- 类型：{exp_type}
- 目标：{target}
- 样本ID：{sample_id}
- 参数：{parameters}

输出要求（JSON字段必须包含hardware、reagents、steps，格式严格如下）：
{{
"hardware": ["plate_washer", "plate_reader", "thermostatic_incubator"],
"reagents": ["PBST", "Capture_Ab", "Detection_Ab", "TMB", "Stop", "BSA", "Standard"],
 "steps": [
    {{
      "action": "Add",
      "reagent": "a",
      "vessel": "96-well-plate",
      "volume": "200 uL"
    }},
    {{
      "action": "Add",
      "reagent": "b",
      "vessel": "reactor",
      "volume": "200 uL"
    }},
    {{
      "action": "Stir",
      "vessel": "reactor",
      "speed": "40"
    }}
  ]
}}

注意：
1. steps必须包含实验核心步骤，参数可用到{params_dilution}和{params_incubate}
2. 不要修改JSON结构，不要添加任何额外内容，替换试剂/步骤中的具体名称,
3. 仅仅参考JSON结构，不要照搬格式的内容
4. steps中的结构先写出动作，再给出参数
5. 输出完直接结束，不要解释
"""

import json
import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# def safe_parse_llm_output(llm_output):
#     """
#     解析 LLM 输出中的 JSON。
#     适配 generate_xdl_protocol 的固定输出结构：
#         { "hardware": [...], "reagents": [...], "steps": [...] }

#     支持：
#     - 前后多余文本
#     - 代码块 ```json ... ```
#     - 未补齐的括号
#     """

#     import json, re

#     # 1) 提取内容
#     raw = getattr(llm_output, "content", llm_output)
#     if not isinstance(raw, str):
#         raw = str(raw)
#     raw = raw.strip()
#     if raw == "":
#         raise json.JSONDecodeError("LLM 输出为空", raw, 0)

#     # 去掉```json``` ```等代码块包裹
#     raw = re.sub(r"^```[\s\S]*?```$", lambda m: m.group(0).strip("`"), raw)

#     # 2) 尝试直接解析（可能本身就是干净 JSON）
#     try:
#         return json.loads(raw)
#     except:
#         pass

#     # 3) 提取第一个 JSON object 或 array （最常见情况）
#     m = re.search(r'(\{[\s\S]*?\}|\[[\s\S]*?\])', raw, flags=re.DOTALL)
#     if m:
#         candidate = m.group(1).strip()
#     else:
#         candidate = raw  # 如果没找到，只能硬解析

#     # 4) 自动补齐括号 —— 避免 "Expecting value"、"char 0"
#     def fix_brackets(s):
#         # {} 补齐
#         diff = s.count("{") - s.count("}")
#         if diff > 0:
#             s += "}" * diff

#         # [] 补齐
#         diff = s.count("[") - s.count("]")
#         if diff > 0:
#             s += "]" * diff

#         return s

#     candidate = fix_brackets(candidate)

#     # 5) unicode 解码（只做一次）避免破坏标签/XML
#     try:
#         decoded = candidate.encode().decode("unicode_escape")
#         # 确保不会把内容完全破坏
#         if len(decoded) >= len(candidate) / 2:
#             candidate = decoded
#     except:
#         pass

#     # 6) 最终解析
#     try:
#         print("LLM 解析候选 JSON=============：", candidate)
#         return json.loads(candidate)
#     except Exception as e:
#         raise json.JSONDecodeError(
#             f"safe_parse_llm_output: JSON parse failed: {e}",
#             candidate,
#             0
#         )


@tool
def generate_xdl_protocol(user_input)-> Dict[str, Any]:
    """
    解析自然语言实验需求，生成完整的XDL协议（自动补全硬件、试剂、步骤）
    """
    prompt = f"""
    你的回复必须严格是一个 JSON 对象，不允许出现任何前缀文字、注释、解释。
    你是实验调度助手，请从以下描述中提取实验信息,输出为JSON，内容为英文，直接输出不用解释：
    - 实验类型(type)
    - 目标物(target)
    - 样品编号(sample_id)
    - 任何其他参数(parameters)
    参考输入输出格式如下,严格遵循格式。根据常识尽可能补全内容，若实在没有的字段给出空： 
    示例1：用户输入"我要做ELISA实验，目标物是TNF-α，样品编号T2024，稀释倍数10，孵育时间1.5h"
    输出：
     {{
     "type": "ELISA",
     "target": "TNF-α",
     "sample_id": "T2024",
     "devices": plate_reader,
     "parameters": {{
       "dilution_factor": 10,
       "incubate_time": "1.5h"
     }}
   }}
    用户输入: {user_input}
    """

    def filter_illegal_chars(llm_output: str) -> str:
        json_pattern = re.compile(r'```(?:json)?\s*\n([\s\S]*?)\n```', re.IGNORECASE)
        s = llm_output.content.encode('utf-8').decode('utf-8')  
        print("解析llm_output内容：==========", s)
        match = json_pattern.search(s)
        if match:
            pure_json = match.group(1).strip()
        else:
            pure_json = s.strip()
        print("解析pure_json1内容：==========", pure_json)
        # 步骤3：容错解析
        try:
            # 额外修复℃编码问题（可选）
            pure_json = pure_json.replace('\xc2\xb0C', '°C')
            print("解析pure_json2内容：==========", pure_json)
            llm_data = json.loads(pure_json)
            print("解析成功：", llm_data)
            return llm_data
        except json.JSONDecodeError as e:
            print("解析失败==========")
            raise e

    response = llm.invoke(prompt)
    raw = response.content.strip()
    if response.content is None or not response.content.strip():
        print("LLM未返回内容response", response)
        return {"status": "error", "message": "LLM未返回内容"}
    exp_info = filter_illegal_chars(response)
    # # 解析 JSON
    # try:
    #     exp_info = json.loads(raw)
    # except json.JSONDecodeError as e:
    #     print("解析失败，LLM返回:", repr(raw))
    #     raise e
    
    print(exp_info)

    # 1. 基础参数补全与校验
    exp_type = exp_info.get("type", "").strip().upper()
    target = exp_info.get("target", "").strip()
    sample_id = exp_info.get("sample_id", f"Sample_{int(time.time())}")
    parameters = exp_info.get("parameters", {})

    # if not exp_type or not target:
    #     print("exp_type, target missing",exp_type,target)
    #     raise ValueError("必须包含 type（实验类型）和 target（目标分子）")

    # 提取关键参数（默认值兜底
    params_dilution = parameters.get("dilution_factor", 1)
    params_incubate = parameters.get("incubate_time", "2h")

    # 2. 调用LLM生成实验细节（使用优化后的提示词）
    logger.info(f"调用LLM生成{exp_type}实验细节...")
    prompt_xdl = LLM_PROMPT_TEMPLATE.format(
        exp_type=exp_type,
        target=target,
        sample_id=sample_id,
        parameters=json.dumps(parameters, ensure_ascii=False),
        params_dilution=params_dilution,
        params_incubate=params_incubate
    )

    # 执行LLM调用并安全解析
    llm_output = llm.invoke(prompt_xdl)
    print("LLM原始输出：", llm_output.content.encode('utf-8') if llm_output.content else b"")
    if llm_output.content is None or not llm_output.content.strip():
        print("LLM未返回内容", llm_output)
        return {"status": "error", "message": "LLM未返回内容"}
    # llm_data = safe_parse_llm_output(llm_output)

    # 过滤非法字符，避免json_lodads报错

    llm_data = filter_illegal_chars(llm_output)


    # llm_data = json.loads(llm_output.content)

    # 3. 生成XDL各部分内容（容错处理：确保字段存在）
    llm_data = {
        "hardware": llm_data.get("hardware", []),
        "reagents": llm_data.get("reagents", []),
        "steps": llm_data.get("steps", [])
    }

    # 3.1 硬件XML（兜底：无硬件时添加默认值）
    if not llm_data["hardware"]:
        llm_data["hardware"] = ["washer:plate_washer", "reader:plate_reader"]
    hardware_xml = "\n      ".join([
        f'<Component id="{h}" type="{h}" />' 
        for h in llm_data["hardware"]
    ])

    # 3.2 试剂XML（兜底：无试剂时添加默认值）
    if not llm_data["reagents"]:
        llm_data["reagents"] = ["PBST:PBST", "Capture_Ab:Capture_Ab", "TMB:TMB", "Stop_Solution:Stop"]
    reagents_xml = "\n      ".join([
        f'<Reagent name="{h}" id="{h}" role="reagent" />' 
        for h in llm_data["reagents"]
    ])

    # 3.3 步骤XML（简化逻辑，避免解析错误）
    procedure_xml = ""
    for step in llm_data["steps"]:
        x = ''
        for i in step.items():
            if i[0] == 'action':
                x += i[1]
                continue
            x += f' {i[0]}="{i[1]}"' 
        procedure_xml +=f"\n     <{x} />"

    # 3.4 元数据XML
    metadata_params = "\n        ".join([
        f'<Parameter name="{k}" value="{v}" />' 
        for k, v in parameters.items()
    ])
    metadata_xml = f"""
      <Experiment target="{target}" sample_id="{sample_id}" type="{exp_type}" generated_time="{time.strftime('%Y-%m-%d %H:%M:%S')}" />
      <Parameters>
        {metadata_params if metadata_params else '        <Parameter name="dilution_factor" value="1" />'}
      </Parameters>"""

    # 4. 填充XDL模板
    xdl_content = XDL_SKELETON.replace("{{hardware}}", hardware_xml)\
                              .replace("{{reagents}}", reagents_xml)\
                              .replace("{{procedure}}", procedure_xml.strip())\
                              .replace("{{metadata}}", metadata_xml.strip())

    # 5. 构造返回结果
    result = {
        "status": "success",
        "exp_type": exp_type,
        "target": target,
        "sample_id": sample_id,
        "xdl_protocol": xdl_content,
        "raw_exp_info": exp_info
    }

    logger.info(f"XDL协议生成完成（样本ID：{sample_id}）")
    return result


@tool
def query_edge_server(
    protocol_type: str,
    broker: str = "101.52.216.165",
    port: int = 18830,  # 与可连客户端一致
    topic: str = "demo/topic",
    subscribe_duration: int = 10,
    case_insensitive: bool = True
) -> Dict[str, Any]:
    """查询可执行指定协议的空闲 Edge Server"""
    available_edges: List[Dict[str, Any]] = []
    client: Optional[mqtt.Client] = None

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("✅ MQTT 连接成功")
            client.subscribe(topic)  # 连接成功后订阅（与可连客户端逻辑一致）
            logger.info(f"📌 已订阅主题：{topic}")
        else:
            logger.error(f"❌ MQTT 连接失败，错误码：{rc}")
            # 错误码说明：0=成功，1=协议版本，2=无效客户端ID，3=服务器不可用，4=用户名密码错误，5=未授权
            error_msg = {
                1: "协议版本不匹配",
                2: "无效客户端ID（可能过长）",
                3: "服务器不可用",
                4: "用户名/密码错误",
                5: "未授权访问"
            }.get(rc, f"未知错误（{rc}）")
            logger.error(f"❌ 错误原因：{error_msg}")

    def on_message(client, userdata, msg):
        try:
            # 兼容两种消息格式：JSON 字典 + 普通字符串
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except json.JSONDecodeError:
                payload = msg.payload.decode("utf-8")
                logger.info(f"📩 收到字符串消息 | 主题：{msg.topic} | 内容：{payload}")
                return  # 非 JSON 消息（如测试字符串），跳过筛选

            logger.info(f"📩 收到 JSON 消息 | 主题：{msg.topic} | 内容：{payload}")

            # 筛选逻辑
            edge_status = payload.get("status", "").strip().lower() or "unknown"
            supported_protocols = payload.get("supported_protocols", [])

            if case_insensitive:
                protocol_matched = protocol_type.lower() in [p.lower() for p in supported_protocols]
            else:
                protocol_matched = protocol_type in supported_protocols

            if edge_status == "idle" and protocol_matched:
                available_edges.append(payload)
                logger.info(f"✅ 添加可用 Edge Server | 累计：{len(available_edges)} 个")
            else:
                logger.info(f"❌ 消息不满足条件 | 状态：{edge_status}（需 idle）| 协议匹配：{protocol_matched}")

        except Exception as e:
            logger.error(f"❌ 处理消息异常：{str(e)}")

    try:

        client = mqtt.Client(
            client_id=f"edge_client_{int(time.time()%1000)}",  # 简化 ID（仅后3位时间戳）
            clean_session=True  # 与可连客户端默认一致
        )

        client.on_connect = on_connect
        client.on_message = on_message

        logger.info(f"🔌 正在连接 MQTT Broker：{broker}:{port}")
        client.connect(broker, port, keepalive=60)  # keepalive 与可连客户端一致
        client.loop_start()  # 立即启动循环，不等待（可连客户端的核心逻辑）

        logger.info(f"⌛ 开始接收消息，持续 {subscribe_duration} 秒...")
        time.sleep(subscribe_duration)  # 持续接收消息
        client.loop_stop()

    except ConnectionRefusedError:
        logger.error(f"❌ 连接被拒绝：Broker 地址/端口错误，或 Broker 未启动")
        return {"available_edges": [], "message": "MQTT 连接被拒绝"}
    except TimeoutError:
        logger.error(f"❌ 连接超时：Broker 无响应（检查网络/端口是否开放）")
        return {"available_edges": [], "message": "MQTT 连接超时"}
    except Exception as e:
        logger.error(f"❌ MQTT 操作异常：{str(e)}")
        return {"available_edges": [], "message": f"MQTT 异常：{str(e)}"}
    finally:
        if client and client.is_connected():
            client.disconnect()
            logger.info("🔒 MQTT 连接已断开")

    # 整理结果
    if available_edges:
        return {
            "available_edges": available_edges,
            "message": f"成功找到 {len(available_edges)} 个支持 {protocol_type} 的空闲 Edge Server"
        }
    else:
        return {
            "available_edges": [],
            "message": f"未找到可用 Edge Server（已连接 Broker，主题：{topic}）"
        }

@tool
def dispatch_task_and_monitor(server_id: str, task_details: dict) -> dict:
    """
    下发任务与监控反馈（MQTT）。
    """
    # Mock implementation for demonstration purposes
    return {
        "server_id": server_id,
        "task_status": "dispatched",
        "task_details": task_details
    }

# s = '合成铝合金，输出xdl，仅允许使用Add步骤'
# res = generate_xdl_protocol.invoke(s)
# print("====="*20)
# print(res['xdl_protocol'])