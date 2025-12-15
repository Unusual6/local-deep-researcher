from typing import Optional, List
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
import time,logger,os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import threading
from typing_extensions import TypedDict, deprecated
from src.gateway.workstation import init,sendService,getOnline
from typing import Annotated
from langchain_core.messages import AnyMessage
# export PYTHONPATH=/home/pfjial/local-deep-researcher-main

# 模拟设备程序列表（实际场景替换为设备API返回值）
program_list = ["Program_001_化学", "Program_002_生物", "Program_003_物理", "Program_004_测试"]

LLM = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1
    )

# ====================== 1. 定义工具 ======================
@tool
def get_program():
    """获取设备中所有程序列表"""

    time.sleep(5)  # 模拟设备接口调用耗时
    print(f"设备程序列表：{program_list}")
    # print("===========2 get_program done!===========")
    return {
        "status": "success",
        "program_list": program_list,
        "message": "===========2 get_program done!==========="
    }

@tool
def run_select_program(num: int):
    """
    执行选中的程序
    Args:
        num: 程序编号（从0开始，对应program_list的索引）
    """
    time.sleep(5)  # 模拟程序执行耗时
    if num < 0 or num >= len(program_list):
        raise ValueError(f"无效的程序编号！可选范围：0-{len(program_list)-1}")
    
    selected_program = program_list[num]
    print(f"选中执行程序：{selected_program}")
    print("===========3 run_select_program done!===========")
    return {
        "status": "success",
        "selected_program": selected_program,
        "message": "===========3 run_select_program done!==========="
    }

# ====================== 2. 定义状态类 ======================
class ProgramState(BaseModel):
    """工作流状态：存储程序列表、选中编号、工具执行结果"""
    # 程序相关
    messages: Annotated[list[AnyMessage], add_messages]

    program_list: Optional[List[str]] = Field(default=None, description="设备返回的程序列表")
    selected_program_num: Optional[int] = Field(default=None, description="人工选择的程序编号")
    get_connect_done: bool = Field(default=False, description="是否已连接服务器")
    # 工具执行状态
    get_program_done: bool = Field(default=False, description="是否已获取程序列表")
    run_program_done: bool = Field(default=False, description="是否已执行选中程序")
    
    # 通信/日志
    error_message: Optional[str] = Field(default=None, description="错误信息")

# ====================== 3. 定义工作流节点 ======================
def Agent_node(state: ProgramState) -> ProgramState:
    messages = state.messages

    response = LLM.invoke(messages)
    state.messages.append(response)
    return state

def get_program_node(state: ProgramState) -> ProgramState:
    """节点1：调用get_program工具，获取程序列表"""
    try:
        # 获取程序列表
        # state.program_list = sendService("getlist",None,None)
        tool_result = get_program.invoke({})  # 调用工具
        state.program_list = tool_result["program_list"]
        state.get_program_done = True
        state.error_message = None
    except Exception as e:
        state.error_message = f"获取程序列表失败：{str(e)}"
        state.get_program_done = False
    return state

def human_input_node(state: ProgramState) -> ProgramState:
    """节点2：人工输入节点（暂停流程，等待用户输入程序编号）"""
    # 打印程序列表，提示用户输入
    print("\n======= 请选择要执行的程序 =======")
    for idx, prog in enumerate(state.program_list):
        print(f"{idx}: {prog}")
    print("------selected_num-------",state.selected_program_num)
    selected_num = int(state.selected_program_num)
    
    if 0 <= selected_num < len(state.program_list):
        state.selected_program_num = selected_num
        state.error_message = None
        return "run_program_node" 
    logger.warning(f"无效输入：selected_program_idx = {idx}，继续等待人工输入")
    return "human_input"
        

def run_program_node(state: ProgramState) -> ProgramState:
    """节点3：调用run_select_program工具，执行选中程序"""
    try:
        data = state.selected_program_num
        # 选中
        sendService("select_exe","exe",data)
        #运行
        sendService("start",None,None) 

        # 调用工具，传入人工选择的编号
        tool_result = run_select_program.invoke({"num": state.selected_program_num})
        state.run_program_done = True
        state.error_message = None
        print(f"程序执行结果：{tool_result['message']}")
    except Exception as e:
        state.error_message = f"执行程序失败：{str(e)}"
        state.run_program_done = False
    return state


def connect_Server_node(state: ProgramState) -> ProgramState:
    """节点3：调用run_select_program工具，执行选中程序"""
    try:
        # 初始化、启动
        # sing_thread = threading.Thread(target=init)
        # sing_thread.start()
        state.get_connect_done = True
        state.error_message = None
        print("=========程序执行结果：连接成功==========")

        # 话题连接
        # getOnline()
        time.sleep(1)

    except Exception as e:
        state.error_message = f"执行程序失败：{str(e)}"
        state.get_connect_done = False
    return state

# ====================== 4. 定义决策节点（流程分支） ======================
def should_continue(state: ProgramState):
    messages = state.messages
    last_message = messages[-1]
    if "开始" in last_message.text:
        return "connect_Server"
    # logger.warning("======结束实验======")
    return END


def check_get_connect_status(state: ProgramState) -> str:
    """决策节点1：判断是否成功获取程序列表"""
    if state.get_connect_done and state.error_message is None:
        return "get_program"  # 成功 → 进入人工输入
    else:
        return "Agent"  # 失败 → 结束流程

def check_get_program_status(state: ProgramState) -> str:
    """决策节点1：判断是否成功获取程序列表"""
    if state.get_program_done and state.error_message is None:
        return "human_input"  # 成功 → 进入人工输入
    else:
        return "connect_Server"  # 失败 → 结束流程

def check_human_input_status(state: ProgramState) -> str:
    """决策节点2：判断是否已获取有效人工输入"""
    if state.selected_program_num is not None and state.error_message is None:
        return "run_program"  # 有有效输入 → 执行程序
    else:
        return "human_input"  # 无有效输入 → 结束流程

# ====================== 5. 构建LangGraph工作流 ======================
# 初始化状态图
graph_builder = StateGraph(ProgramState)

graph_builder.add_node("Agent", Agent_node)     
graph_builder.add_node("get_program", get_program_node)      
graph_builder.add_node("human_input", human_input_node)       
graph_builder.add_node("run_program", run_program_node)      
graph_builder.add_node("connect_Server", connect_Server_node)  

graph_builder.add_edge(START, "Agent")
graph_builder.add_conditional_edges("Agent", should_continue, ["connect_Server", END])
graph_builder.add_edge("connect_Server", "get_program")

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
        "connect_Server":"connect_Server"
    }
)

graph_builder.add_conditional_edges(
    "human_input",
    check_human_input_status,
    {
        "human_input":"human_input",
        "run_program": "run_program",
        # END: END
    }
)

# 执行程序后 → 结束流程
graph_builder.add_edge("run_program", "get_program")

# 编译工作流
graph = graph_builder.compile(
    interrupt_before=["human_input"]
)

# ====================== 6. 运行工作流 ======================
if __name__ == "__main__":
    # # 初始化状态（空状态）
    # initial_state = ProgramState()
    
    # # 执行工作流
    # final_state = graph.invoke(initial_state)
    
    # # 打印最终状态
    # print("\n======= 工作流执行完成 =======")


    res = graph.invoke(
        {"messages": [{"role": "user", "content": "开始实验"}]},
        thread_id="thread-1"
    )
    print(res)