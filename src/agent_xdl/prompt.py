
XDL_prompt = """
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