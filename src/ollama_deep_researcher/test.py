import json
import time,os
from typing import Dict, Any
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import Field
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 初始化Ollama LLM（确保本地已启动Ollama，且已拉取模型）
def init_global_llm():
    """初始化全局 LLM 实例（从环境变量读取配置，避免硬编码）"""
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "Qwen3-32B-FP8"),
        api_key=os.getenv("LLM_API_KEY", "1756891290237NvNud1IzoEnGtlNncoB1uWl"),
        openai_api_base=os.getenv("LLM_API_BASE", "http://120.204.73.73:8033/api/ai-gateway/v1"),
        temperature=0.1
    )

# 全局 LLM 实例（模块加载时自动初始化）
llm = init_global_llm()

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

def safe_parse_llm_output(llm_output: str) -> Dict[str, Any]:
    """安全解析LLM输出的JSON，处理格式错误"""
    try:
        # 清理可能的多余字符（引号、换行、空格）
        clean_output = llm_output.content.strip()\
            .replace("'", '"')\
            .replace("\n", "")\
            .replace("\t", "")\
            # .replace(" ", "")  # 去除所有空格（避免格式问题）
        # 确保JSON格式正确
        if not clean_output.startswith("{"):
            clean_output = "{" + clean_output
        if not clean_output.endswith("}"):
            clean_output = clean_output + "}"
        # 解析JSON
        return json.loads(clean_output)
    except Exception as e:
        logger.error(f"LLM输出解析失败：{e}，原始输出：{llm_output}")
        # 强制返回默认数据（避免KeyError）
        return {
            "hardware": ["washer:plate_washer", "reader:plate_reader", "incubator:thermostatic_incubator"],
            "reagents": ["PBST:PBST", "Capture_Ab:Capture_Anti_IFNγ", "Detection_Ab:HRP_Anti_IFNγ", 
                        "TMB:TMB", "Stop_Solution:Stop", "BSA:BSA", "Standard:IFNγ_Standard"],
            "steps": [
                "1.加Capture_Ab到96孔板100uL",
                "2.4°C孵育16h",
                "3.PBST洗涤3次200uL/次",
                "4.加BSA封闭液200uL37°C孵育1h",
                "5.PBST洗涤3次",
                "6.加样本/标准品100uL稀释倍数{params_dilution}",
                "7.37°C孵育{params_incubate}",
                "8.PBST洗涤3次",
                "9.加Detection_Ab100uL",
                "10.37°C孵育1h",
                "11.PBST洗涤5次",
                "12.加TMB50uL",
                "13.37°C避光孵育15min",
                "14.加Stop_Solution50uL",
                "15.450nm读数参考630nm"
            ]
        }

@tool
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
    输出为JSON，内容为英文,参考输入输出格式如下,严格遵循格式。根据常识尽可能补全内容，若实在没有的字段给出空： 
    示例1：用户输入"我要做ELISA实验，目标物是TNF-α，样品编号T2024，稀释倍数10，孵育时间1.5h"
    输出：
   {{exp_info = {{
     "type": "ELISA",
     "target": "TNF-α",
     "sample_id": "T2024",
     "devices": plate_reader,
     "parameters": {{
       "dilution_factor": 10,
       "incubate_time": "1.5h"
     }}
   }}}}
    用户输入: {user_input}
    """
    response = llm.predict(prompt)
    try:
        return json.loads(response)
    except Exception:
        return {"type": "ELISA", "target": "IFN-γ", "sample_id": "unknown"}


@tool
def generate_xdl_protocol(user_input)-> Dict[str, Any]:
    """
    解析自然语言实验需求，生成完整的XDL协议（自动补全硬件、试剂、步骤）
    """
    prompt = f"""
    你是实验调度助手，请从以下描述中提取实验信息：
    - 实验类型(type)
    - 目标物(target)
    - 样品编号(sample_id)
    - 任何其他参数(parameters)
    输出为JSON，内容为英文,参考输入输出格式如下,严格遵循格式。根据常识尽可能补全内容，若实在没有的字段给出空： 
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
    response = llm.predict(prompt)
    
    exp_info = json.loads(response)


    # 1. 基础参数补全与校验
    exp_type = exp_info.get("type", "").strip().upper()
    target = exp_info.get("target", "").strip()
    sample_id = exp_info.get("sample_id", f"Sample_{int(time.time())}")
    parameters = exp_info.get("parameters", {})

    if not exp_type or not target:
        raise ValueError("必须包含 type（实验类型）和 target（目标分子）")

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

    # 替换步骤中的参数占位符（确保参数生效）
    llm_data["steps"] = [
        step.replace("{params_dilution}", str(params_dilution))
            .replace("{params_incubate}", str(params_incubate))
        for step in llm_data["steps"]
    ]

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


# 测试调用（仅输入极简参数）
if __name__ == "__main__":

    try:
        # s={
        #     "type": "ELISA",
        #     "target": "PD-L1",
        #     "sample_id": "S321",
        #     "devices": "plate_reader",
        #     "parameters": {}
        # }

        s = '帮我检测样品S321的PD-L1浓度,先解析实验需求'
        # res = parse_experiment_description.invoke(input=s)
        r1 = generate_xdl_protocol.invoke(s)
        logger.info(f"解析结果: {r1}")
    except Exception as e:
        logger.error(f"调用工具时出错: {e}")


