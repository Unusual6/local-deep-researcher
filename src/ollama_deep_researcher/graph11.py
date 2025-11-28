# src/agent_xdl/subgraph_xdl.py
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import RunnableConfig
from typing import TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage

# 1. 子图状态（可扩展 MessagesState，也可用自定义状态）
class XDLState(MessagesState, TypedDict):
    sample_id: str  # 子图专属字段：样本ID
    xdl_result: dict  # 存储XDL生成结果
    retry_count: int  # 重试次数

# 2. 子图节点：生成XDL（复用你之前的工具函数）
def generate_xdl_node(state: XDLState) -> XDLState:
    from src.agent_xdl.tools1 import generate_xdl_protocol
    
    # 提取参数（从子图状态中取）
    target = next(msg.content for msg in reversed(state["messages"]) if isinstance(msg, HumanMessage))
    sample_id = state["sample_id"]
    
    # 调用工具生成XDL
    xdl_result = generate_xdl_protocol(
        exp_type="ELISA", target=target, sample_id=sample_id,
        parameters={}, params_dilution="1:1000", params_incubate="37°C, 1h"
    )
    
    # 更新子图状态
    return {
        **state,
        "xdl_result": xdl_result,
        "retry_count": state["retry_count"] + 1 if xdl_result["status"] == "failed" else 0
    }

# 3. 子图决策节点：判断是否重试/终止
def xdl_decide_next(state: XDLState) -> str:
    if state["xdl_result"].get("status") == "success":
        return "end"
    if state["retry_count"] >= 2:
        return "end"
    return "generate_xdl"

# 4. 构建并编译子图（核心：编译后成为Runnable，可被主图调用）
def build_xdl_subgraph() -> StateGraph:
    builder = StateGraph(XDLState)
    
    # 添加子图节点
    builder.add_node("generate_xdl", generate_xdl_node)
    builder.add_node("end", lambda x: x)  # 终止节点
    
    # 定义子图流转
    builder.set_entry_point("generate_xdl")
    builder.add_conditional_edges("generate_xdl", xdl_decide_next)
    builder.add_edge("end", "__end__")
    
    # 编译子图（返回Runnable）
    return builder.compile()

# 实例化子图（全局可调用）
xdl_subgraph = build_xdl_subgraph()