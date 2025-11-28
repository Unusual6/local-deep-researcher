# 修正版：更稳健的 ToolNode 调用 + 简单去重 (in-memory debounce)
import time
import os
from typing import TypedDict, Sequence, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.tools import Tool

# -------------------- 工具定义 --------------------
def weather_tool(city: str) -> str:
    return f"{city} 今日天气：晴，气温 22~30℃，风力 2 级"

weather_tool_chain = Tool(
    name="weather_tool",
    func=weather_tool,
    description="用于查询指定城市的天气信息，入参为城市名称（字符串）"
)
tools = [weather_tool_chain]
tool_node = ToolNode(tools)

# -------------------- 模型初始化（不要硬编码 key） --------------------
llm_api_key = os.environ.get("OPENAI_API_KEY", None)
llm = ChatOpenAI(
    model="Qwen3-32B-FP8",
    api_key='1756891290237NvNud1IzoEnGtlNncoB1uWl',
    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
    temperature=0.6,
)

# -------------------- 数据模型 --------------------
class ToolInvocation(BaseModel):
    tool: str
    kwargs: Dict[str, Any]
    id: Optional[str] = None

class GraphState(TypedDict):
    messages: List[str]
    tool_result: str
    city: str

# -------------------- 简单去重（防抖） --------------------
# 保存最近一次对相同(thread,input)的时间戳
_recent_calls: Dict[str, float] = {}

def debounce_check(key: str, interval: float = 1.0) -> bool:
    """返回 True 表示允许执行；False 表示被 debounce 拦截"""
    now = time.time()
    last = _recent_calls.get(key)
    if last is None or (now - last) > interval:
        _recent_calls[key] = now
        return True
    return False

# -------------------- 决策节点（构造 ToolInvocation） --------------------
from langchain_core.messages import AIMessage

def decide_to_call_tool(state: GraphState) -> dict:
    tool_call = {
        "name": "weather_tool",
        "args": {"city": state["city"]},
        "id": "call-weather-1"
    }

    ai_msg = AIMessage(
        content="",
        tool_calls=[tool_call]
    )

    return {"messages": [ai_msg]}


# -------------------- 工具调用子图节点 --------------------
def call_tool_node(state: GraphState) -> GraphState:
    # 1. 生成带 tool_call 的 AIMessage
    payload = decide_to_call_tool(state)

    # 2. ToolNode 执行工具（关键）
    raw = tool_node.invoke(payload)  
    # 返回格式：
    # {"messages": [AIMessage(tool_call=...), ToolMessage(result)]}

    tool_msg = raw["messages"][-1]  # ToolMessage
    state["tool_result"] = tool_msg.content
    state["messages"].append(f"工具调用结果：{tool_msg.content}")

    return state


# -------------------- 构建子图 & 主图 --------------------
subgraph = StateGraph(GraphState)
subgraph.add_node("call_tool", call_tool_node)
subgraph.add_edge(START, "call_tool")
subgraph.add_edge("call_tool", END)
tool_subgraph = subgraph.compile()

main_graph = StateGraph(GraphState)
main_graph.add_node("tool_flow", tool_subgraph)
main_graph.add_edge(START, "tool_flow")
main_graph.add_edge("tool_flow", END)
main_app = main_graph.compile()

# -------------------- 测试运行 --------------------
# if __name__ == "__main__":
#     input_state = {
#         "messages": ["用户请求查询北京天气"],
#         "tool_result": "",
#         "city": "北京"
#     }
#     result = main_app.invoke(input_state)
#     print("=== 最终状态 ===")
#     print(f"对话消息：{result['messages']}")
#     print(f"工具调用结果：{result['tool_result']}")
