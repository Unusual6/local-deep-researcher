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


# 帮我检测样品S321的PD-L1浓度,输出xdl.只解析实验需求，输出结果
# 我要做合成磷酸铁锂的实验，输出xdl,先解析实验需求
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
你是专业生物实验工程师，仅根据以下信息生成{exp_type}实验的硬件、试剂、步骤，严格按照指定JSON格式输出，不要任何额外文字、注释、换行！

实验信息：
- 类型：{exp_type}
- 目标：{target}
- 样本ID：{sample_id}
- 参数：{parameters}

输出要求（JSON字段必须包含hardware、reagents、steps，格式严格如下）：
{{
"hardware": ["washer:plate_washer", "reader:plate_reader", "incubator:thermostatic_incubator"],
"reagents": ["PBST:PBST", "Capture_Anti_IFNγ:Capture_Ab", "HRP_Anti_IFNγ:Detection_Ab", "TMB:TMB", "Stop_Solution:Stop", "BSA:BSA", "IFNγ_Standard:Standard"],
"steps": [<Add reagent="a" vessel="96-well-plate" volume="200 uL" />'，
          <Add reagent="b" vessel="reactor" volume="200 uL" />'
          <Stir vessel="reactor" speed="40" />'
            ]
}}

注意：
1. steps必须包含实验核心步骤，参数可用到{params_dilution}和{params_incubate}
2. 不要修改JSON结构，不要添加任何额外内容，替换试剂/步骤中的具体名称,
3. 仅仅参考JSON结构，不要照搬格式的内容
4. steps中的结构先写出动作，再给出参数，中间隔开
5. 输出完直接结束，不要解释
"""

import json
import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def safe_parse_llm_output(llm_output: Any) -> Dict[str, Any]:
    """
    Robust parser for LLM outputs that are meant to be JSON but may contain
    embedded XML/self-closing tags with unescaped quotes, double-quoting, or
    various backslash-escape artifacts.

    Returns a python dict if successful, otherwise raises JSONDecodeError with
    helpful debug printouts.
    """
    # 1) get raw text
    if hasattr(llm_output, "content"):
        raw = llm_output.content
    else:
        raw = llm_output if isinstance(llm_output, str) else str(llm_output)

    raw = raw.strip()

    # helper: try json loads and return if ok
    def try_load(s: str):
        try:
            return json.loads(s)
        except Exception as e:
            raise

    # small utility: escape unescaped quotes inside a tag <...>
    def escape_unescaped_quotes_in_tag(tag: str) -> str:
        # tag looks like <...> or <.../>
        inner = tag[1:-1]
        # replace any " that is not already escaped (not preceded by backslash) with \"
        inner_escaped = re.sub(r'(?<!\\)"', r'\\"', inner)
        return f"<{inner_escaped}>"

    # utility: wrap a tag in quotes and ensure internal quotes are escaped
    def wrap_tag_as_json_string(tag: str) -> str:
        # tag may be "<.../>" without quotes; we want "\"<.../>\""
        escaped_tag = escape_unescaped_quotes_in_tag(tag)
        # now ensure backslashes are single (we'll not unescape here)
        return f'"{escaped_tag}"'

    # Attempt sequence of progressively more aggressive fixes
    attempts = []

    # attempt 0: raw attempt
    attempts.append(("raw", raw))

    # attempt 1: if there are stray leading/trailing content that are not JSON,
    # try to extract first {...} block
    m = re.search(r'\{.*\}', raw, flags=re.DOTALL)
    if m:
        attempts.append(("extract_braces", m.group(0)))

    # attempt 2: unicode escape decode (handles double-escaped sequences like \\\" -> \")
    try:
        decoded = raw.encode("utf-8").decode("unicode_escape")
        if decoded != raw:
            attempts.append(("unicode_escape_decoded", decoded))
    except Exception:
        pass

    # attempt 3: reduce multiple backslashes (e.g. \\\\" -> \\" ) iteratively
    s = raw
    for i in range(3):
        s2 = re.sub(r'\\\\{2,}', lambda m: '\\\\' * (len(m.group(0)) // 2), s)
        if s2 != s:
            attempts.append((f"reduce_backslashes_{i}", s2))
            s = s2

    # attempt 4: handle patterns of double-double-quote around tags, and wrap unquoted tags
    def normalize_tags(s: str) -> str:
        # 4.1 remove accidental double-double quotes: ""<tag/>"" -> "<tag/>"
        s = re.sub(r'""\s*(<[^>]+/?>)\s*""', r'"\1"', s)

        # 4.2 fix occurrences like '"<tag/>"",""<tag/>"' -> '"<tag/>","<tag/>"'
        s = s.replace('",""', '","')

        # 4.3 wrap unquoted tags <.../> -> "<.../>"
        # But only wrap when tag is not already quoted (negative lookbehind/lookahead)
        s = re.sub(
            r'(?<!")(<[^>"\]]+?/?>)(?!")',
            lambda m: wrap_tag_as_json_string(m.group(1)),
            s
        )

        # 4.4 ensure tags that ended up with escaped quotes have their inner quotes escaped
        # (already handled by wrap_tag_as_json_string / escape_unescaped_quotes_in_tag)

        # 4.5 normalize awkward sequences like '", "<' -> '"," <' -> keep as '"," <' is okay JSON if inner has quotes
        s = re.sub(r'",\s*"<', '", "<', s)

        return s

    attempts.append(("normalize_tags_initial", normalize_tags(raw)))

    # attempt 5: try to progressively apply normalization to the decoded attempts too
    for name, candidate in list(attempts):
        try:
            # quick direct load
            return json.loads(candidate)
        except Exception:
            pass

    # Now try normalized variants in a safer loop
    candidates_tried = set()
    for name, candidate in attempts:
        # 1) normalized once
        n1 = normalize_tags(candidate)
        if n1 not in candidates_tried:
            candidates_tried.add(n1)
            try:
                return json.loads(n1)
            except Exception:
                pass
        # 2) escape internal quotes inside tags more aggressively
        # find tags and replace them with safe strings
        def replacer(m):
            tag = m.group(0)
            inner = tag[1:-1]
            inner_escaped = re.sub(r'(?<!\\)"', r'\\"', inner)
            return f'"<{inner_escaped}>"'
        n2 = re.sub(r'<[^>]+/?>', replacer, candidate)
        if n2 not in candidates_tried:
            candidates_tried.add(n2)
            try:
                return json.loads(n2)
            except Exception:
                pass

    # Final brute-force attempt:
    #  - replace all occurrences of <...> with a JSON-safe quoted and escaped version
    # This is aggressive and will change non-tag content, but only used as last resort.
    def brute_force_all_tags(s: str) -> str:
        def rep(m):
            tag = m.group(0)
            inner = tag[1:-1]
            inner_escaped = re.sub(r'(?<!\\)"', r'\\"', inner)
            return f'"<{inner_escaped}>"'
        return re.sub(r'<[^>]+/?>', rep, s)

    final_candidate = brute_force_all_tags(raw)
    try:
        return json.loads(final_candidate)
    except Exception as final_exc:
        # Provide detailed debug information
        debug_info = {
            "error": str(final_exc),
            "raw_snippet": raw[:1000],
        }
        logger.error("safe_parse_llm_output failed: %s", debug_info)
        # raise a JSONDecodeError with more context
        raise json.JSONDecodeError(
            f"safe_parse_llm_output: all attempts failed. last error: {final_exc}",
            raw,
            0
        )

@tool
def generate_xdl_protocol(user_input)-> Dict[str, Any]:
    """
    解析自然语言实验需求，生成完整的XDL协议（自动补全硬件、试剂、步骤）
    """
    prompt = f"""
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
    response = llm.invoke(prompt)
    
    exp_info = json.loads(response.content)
    print(exp_info)

    # 1. 基础参数补全与校验
    exp_type = exp_info.get("type", "").strip().upper()
    target = exp_info.get("target", "").strip()
    sample_id = exp_info.get("sample_id", f"Sample_{int(time.time())}")
    parameters = exp_info.get("parameters", {})

    # if not exp_type or not target:
    #     print("exp_type, target missing",exp_type,target)
    #     raise ValueError("必须包含 type（实验类型）和 target（目标分子）")

    # 提取关键参数（默认值兜底）
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
    print("LLM原始输出：", llm_output)
    llm_data = safe_parse_llm_output(llm_output)

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
        f'<Component id="{h.split(":")[0]}" type="{h.split(":")[1]}" />' 
        for h in llm_data["hardware"]
    ])

    # 3.2 试剂XML（兜底：无试剂时添加默认值）
    if not llm_data["reagents"]:
        llm_data["reagents"] = ["PBST:PBST", "Capture_Ab:Capture_Ab", "TMB:TMB", "Stop_Solution:Stop"]
    reagents_xml = "\n      ".join([
        f'<Reagent name="{h.split(":")[0]}" id="{h.split(":")[1]}" />' 
        for h in llm_data["reagents"]
    ])

    # 3.3 步骤XML（简化逻辑，避免解析错误）
    procedure_xml = ""
    for step in llm_data["steps"]:
        procedure_xml +=f"\n      {step}"

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

# s = '合成磷酸铁锂的实验，输出xdl'
# res = generate_xdl_protocol.invoke(s)
# print("====="*20)
# print(res['xdl_protocol'])