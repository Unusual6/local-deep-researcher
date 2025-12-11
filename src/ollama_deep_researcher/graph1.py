import uuid,os
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage,ToolMessage
# from ollama_deep_researcher.tools import llm_calculator_tool,generate_xdl_protocol
from src.ollama_deep_researcher.tools import query_edge_server,dispatch_task_and_monitor
from src.agent_xdl.tools1 import llm_calculator_tool,generate_xdl_protocol,weather_tool
# from langgraph.checkpoint.sqlite import SqliteSaver

# export PYTHONPATH=/home/pfjial/local-deep-researcher-main

tools = [llm_calculator_tool,generate_xdl_protocol,query_edge_server,dispatch_task_and_monitor,weather_tool]
tool_node = ToolNode(tools)

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END
# 1764728646727FBys1MQS2i7TX48XcRbrLxg
model_with_tools = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1
    ).bind_tools(tools=tools)

def call_model(state: MessagesState) -> MessagesState:
    messages = state["messages"]
    
    # 🔴 核心判断：是否已经执行完所有工具且结果符合要求
    # 1. 找到最后一条工具执行结果（ToolMessage）
    tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]
    # 2. 找到最后一条Agent消息（判断是否还有新工具调用）
    ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    
    # 终止条件：有工具执行结果 + 最后一条AI消息无新工具调用 → 直接返回，跳过LLM整理
    if tool_messages and ai_messages:
        last_ai_msg = ai_messages[-1]
        # 检查最后一条AI消息是否有未执行的tool_calls
        if not getattr(last_ai_msg, "tool_calls", None):
            # 无新工具调用 → 直接返回当前state，不调用LLM
            return state
    
    # 🔴 仅当需要继续处理时，才调用LLM
    response = model_with_tools.invoke(messages)

    # 自动补上缺失的 tool_call_id
    if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
        for tool_call in response.tool_calls:
            if not tool_call.get("id"):
                tool_call["id"] = f"call_{uuid.uuid4().hex[:8]}"

    state['messages'].append(response)
    return state

# checkpointer = SqliteSaver.from_conn_string(
#     "file:./langgraph_chat.db?mode=rwc"
# )

graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
app = graph.compile()
# app = graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    # res = app.invoke(
    #     {"messages": [{"role": "user", "content": "计算下897*678"}]},
    #     thread_id="thread-1"
    # )
    # print(res)
    print("===="*20)
    for chunk in app.stream(
            {"messages": [{"role": "user", "content": "合成氧化锆的混合前驱体阶段，生成实验步骤中的核心动作以混合为主的xdl"}]},
            stream_mode="updates"):
        pass
        # print(chunk)

    # print(f"SQLite DB 写入路径：./langgraph_chat.db")