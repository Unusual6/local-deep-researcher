from typing import Optional, List,Dict,Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
import time,logger,os,json,uuid
from langchain_openai import ChatOpenAI
import threading
from langgraph.types import interrupt
from src.O_devices.zuofei.workstation import init,sendService,getOnline
from src.O_devices.zuofei.zuofei_tools import program_manager
from typing import Annotated
from langchain_core.messages import AnyMessage,AIMessage, SystemMessage, HumanMessage
# export PYTHONPATH=/home/pfjial/local-deep-researcher-main

AGENT_SYSTEM_PROMPT = """
你是实验设备控制系统的意图解析器。

你的任务：
- 判断用户是否要启动实验
- 只输出 intent
"""


AGENT_USER_PROMPT = """
用户输入：
{user_input}

请输出：
{{
  "intent": "start | not_start",
  "reason": "一句话解释"
}}
"""

LLM = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1)

# ====================== 2. 定义状态类 ======================
class ProgramState(BaseModel):
    """工作流状态：存储程序列表、选中编号、工具执行结果"""
    # 程序相关
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Literal["start", "not_start"] = None
    program_list: Optional[Dict] = Field(default=None, description="设备返回的程序列表（字典格式）")
    selected_program_num: Optional[int] = Field(default=None, description="人工选择的程序编号")
    connected: bool = False 
    # 工具执行状态
    get_program_done: bool = Field(default=False, description="是否已获取程序列表")
    run_program_done: bool = Field(default=False, description="是否已执行选中程序")
    
    # 通信/日志
    error_message: Optional[str] = Field(default=None, description="错误信息")

# ====================== 3. 定义工作流节点 ======================
def Agent_node(state: ProgramState) -> ProgramState:
    user_input = state.messages[-1].content

    messages = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=AGENT_USER_PROMPT.format(
                connected=state.connected,
                user_input=user_input
            )
        )
    ]

    resp = LLM.invoke(messages)

    try:
        data = json.loads(resp.content)
        intent = data.get("intent", "not_start")
    except Exception:
        intent = "not_start"

    state.intent = "start" if intent == "start" else "not_start"


    # —— 前置条件硬校验 ——
    if not state.connected and intent not in ("connect", "start"):
        state.intent = "connect"
        reply = "⚠️ 当前尚未连接服务器，请先执行连接操作。"
    else:
        state.intent = intent
        reply = f"✅ 已识别意图：{intent}， 准备开启实验"

    # state.messages.append(AIMessage(content=reply))
    first = uuid.uuid4().hex[:8]
    second = uuid.uuid4().hex[:8]
    state.messages.append(AIMessage(content=json.dumps({
        "blocks":[ {
            "title": "",
            "block_id": first,
            "content": {
                "text": "设备调度",
                "status": "running代表运行中，done代表此节点结束"
            },
            "content_type": "foldable_title", 
            "position_type": "left",
            "stream_mode": "updates",
            "parent": "",
            "right": ""
        },
        {
            "title": "",
            "block_id": second,
            "content": {
                "abstract": "",
                "text": reply,
                "tag": "SIMPLE"
            },
            "content_type": "foldable_markdown",
            "position_type": "left",
            "stream_mode": "updates",
            "parent": "first",
            "right": ""
        }],
        "status":'running'
    })))
    return state

def logInfo(msg):
    print("消息:"+msg)

def get_program_node(state: ProgramState) -> ProgramState:
    """节点1：调用get_program工具，获取程序列表"""
    try:
        # 获取程序列表
        sendService("getlist",None,None)
        # program_manager.program_list = {'1':'123'}
        # logInfo(f"[c.py] 发送getlist指令，开始等待 时间：{time.time()}")
        # time.sleep(10)
        timeout = 20  # 超时时间（秒），根据设备响应速度调整
        start_time = time.time()
        program_list = []
        while time.time() - start_time < timeout:
            # 每次轮询都获取最新的program_list
            current_list = program_manager.program_list
            if current_list:  # 拿到数据，退出循环
                program_list = current_list
                break
            time.sleep(0.5)  # 轮询间隔，避免占用CPU
        
        # 赋值并校验结果
        if program_list:
            state.program_list = program_list
            print(f"✅ 获取到程序列表：{state.program_list}")
        else:
            state.error_message = f"❌ 超时{timeout}秒未获取到程序列表"
            print(state.error_message)

        # state.program_list = program_manager.program_list
        if state.program_list is not None:
            state.get_program_done = True
            state.error_message = None
        # 先处理程序列表，生成Markdown表格
        program_list = state.program_list
        # 1. 构建表格头部
        # 2. 构建表格内容（按序号排序，保证1~14顺序展示）
        table_rows = ""
        # 按数字升序遍历键（避免字典无序问题）
        sorted_keys = sorted(program_list.keys(), key=lambda k: int(k))
        for idx in sorted_keys:
            table_rows += f"{idx}.{program_list[idx]} \n"

    # 生成美化后的提示语
        prompt_msg = f"""
        🔍 等待人工输入程序编号：
        - 程序列表：
        {table_rows.rstrip()}  

        - 操作步骤如下：
        1. 选择程序执行，请输入序号：1 ~ {len(program_list)}
        2. 若退出执行，输入序号0
        """

        # state.messages.append(
        #     AIMessage(content=prompt_msg)
        # )
        first = uuid.uuid4().hex[:8]
        second = uuid.uuid4().hex[:8]
        state.messages.append(AIMessage(content=json.dumps({
            "blocks":[ {
                "title": "",
                "block_id": first,
                "content": {
                    "text": "程序列表获取",
                    "status": "done"
                },
                "content_type": "foldable_title", 
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "",
                "right": ""
            },
            {
                "title": "",
                "block_id": second,
                "content": {
                    "abstract": "",
                    "text": prompt_msg,
                    "tag": "SIMPLE"
                },
                "content_type": "foldable_markdown",
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "first",
                "right": ""
            }],
            "status":'running'
        })))
    except Exception as e:
        state.error_message = f"获取程序列表失败：{str(e)}"
        state.get_program_done = False
        first = uuid.uuid4().hex[:8]
        second = uuid.uuid4().hex[:8]
        state.messages.append(AIMessage(content=json.dumps({
            "blocks":[ {
                "title": "",
                "block_id": first,
                "content": {
                    "text": "程序列表获取失败",
                    "status": "done"
                },
                "content_type": "foldable_title", 
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "",
                "right": ""
            },
            {
                "title": "",
                "block_id": second,
                "content": {
                    "abstract": "",
                    "text": f"获取程序列表失败：{str(e)}",
                    "tag": "SIMPLE"
                },
                "content_type": "foldable_markdown",
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "first",
                "right": ""
            }],
            "status":'running'
        })))
    return state

def human_input_node(state: ProgramState) -> ProgramState:
    # state.selected_program_num = 7
    num = interrupt("select the num of programs")
    state.selected_program_num = num
    return state

        

def run_program_node(state: ProgramState) -> ProgramState:
    try:
        num = state.selected_program_num
        # 选中
        sendService("select_exe","exe",state.program_list[str(num)])
        time.sleep(2)
        # #运行
        sendService("start",None,None) 
        # state.messages.append(
        #     AIMessage(content=f"""{state.program_list[str(num)]} 程序正在运行中.....""")
        # ) 
        state.run_program_done = True
        state.error_message = None
        first = uuid.uuid4().hex[:8]
        second = uuid.uuid4().hex[:8]
        state.messages.append(AIMessage(content=json.dumps({
        "blocks":[ {
            "title": "",
            "block_id": first,
            "content": {
                "text": "运行程序",
                "status": "running"
            },
            "content_type": "foldable_title", 
            "position_type": "left",
            "stream_mode": "updates",
            "parent": "",
            "right": ""
        },
        {
            "title": "",
            "block_id": second,
            "content": {
                "abstract": "",
                "text": f"""{state.program_list[str(num)]} 程序正在运行中.....""",
                "tag": "SIMPLE"
            },
            "content_type": "foldable_markdown",
            "position_type": "left",
            "stream_mode": "updates",
            "parent": "first",
            "right": ""
        }],
        "status":'running'
    })))

    except Exception as e:
        state.error_message = f"执行程序失败：{str(e)}"
        state.run_program_done = False
    return state

def parse_human_input_node(state: ProgramState) -> ProgramState:
    try:
        if state.selected_program_num is not None:
            state.selected_program_num = int(state.selected_program_num)
    except Exception:
        state.error_message = "程序编号必须是数字"
    return state


def connect_Server_node(state: ProgramState) -> ProgramState:
    try:
        # 初始化、启动
        sing_thread = threading.Thread(target=init)
        sing_thread.start()
        state.error_message = None
        time.sleep(2)
        # 话题连接
        getOnline()
        time.sleep(2)
        state.connected = True
        state.error_message = None

        # state.messages.append(
            # AIMessage(content=" 服务器连接成功，可以继续操作。")
        # )

        first = uuid.uuid4().hex[:8]
        second = uuid.uuid4().hex[:8]
        state.messages.append(AIMessage(content=json.dumps({
            "blocks":[ {
                "title": "",
                "block_id": first,
                "content": {
                    "text": "连接服务器",
                    "status": "done"
                },
                "content_type": "foldable_title", 
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "",
                "right": ""
            },
            {
                "title": "",
                "block_id": second,
                "content": {
                    "abstract": "",
                    "text": " 服务器连接成功，可以继续操作。",
                    "tag": "SIMPLE"
                },
                "content_type": "foldable_markdown",
                "position_type": "left",
                "stream_mode": "updates",
                "parent": "first",
                "right": ""
            }],
            "status":'running'
        })))
    except Exception as e:
        state.connected = False
        state.error_message = f"执行程序失败：{str(e)}"
        state.messages.append(
            AIMessage(content=f"❌ 服务器连接失败：{e}")
        )
    return state

# ====================== 4. 定义决策节点（流程分支） ======================
def route_by_intent(state):
    if state.intent == "start":
        return "connect_Server"
    return END


def check_get_connect_status(state: ProgramState) -> str:
    """决策节点1：判断是否成功获取程序列表"""
    if state.connected and state.error_message is None:
        return "get_program"  # 成功 → 进入人工输入
    else:
        return "Agent"  # 失败 → 结束流程

def check_get_program_status(state):
    if state.error_message is None:
        return "human_input"  
    else: 
        return END

def check_human_input_status(state: ProgramState) -> str:
    num = state.selected_program_num

    if num == 0:
        return END

    valid_nums = [int(k) for k in state.program_list.keys()]
    if num in valid_nums:
        return "run_program"

    return "human_input"


# ====================== 5. 构建LangGraph工作流 ======================
graph_builder = StateGraph(ProgramState)

graph_builder.add_node("Agent", Agent_node)     
graph_builder.add_node("get_program", get_program_node)      
graph_builder.add_node("human_input", human_input_node)       
graph_builder.add_node("run_program", run_program_node)      
graph_builder.add_node("connect_Server", connect_Server_node)  

graph_builder.add_edge(START, "Agent")
graph_builder.add_conditional_edges("Agent", route_by_intent, ["connect_Server", END])
graph_builder.add_edge("run_program", "get_program")

graph_builder.add_node("parse_human_input", parse_human_input_node)

graph_builder.add_edge("human_input", "parse_human_input")

graph_builder.add_conditional_edges(
    "parse_human_input",
    check_human_input_status,
    {
        "human_input": "human_input",
        "run_program": "run_program",
        END: END
    }
)


graph_builder.add_conditional_edges(
    "connect_Server",
    check_get_connect_status,
    {
        "get_program": "get_program",
        "Agent": "Agent"
    }
)
graph_builder.add_conditional_edges(
    "get_program",
    check_get_program_status,
    {
        "human_input": "human_input",
        END:END
        # "get_program":"get_program"
    }
)

graph = graph_builder.compile(
    # interrupt_before=["human_input"]
)

if __name__ == "__main__":

    res = graph.invoke(
        {"messages": [{"role": "user", "content": "开启zuofei"}]}
    )
    print(res)