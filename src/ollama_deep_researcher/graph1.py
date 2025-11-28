import uuid
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage
# from ollama_deep_researcher.tools import llm_calculator_tool,generate_xdl_protocol
from ollama_deep_researcher.tools import query_edge_server,dispatch_task_and_monitor
from src.agent_xdl.tools1 import llm_calculator_tool,generate_xdl_protocol
# from langgraph.checkpoint.sqlite import SqliteSaver

# export PYTHONPATH=/home/pfjial/local-deep-researcher-main

tools = [llm_calculator_tool,generate_xdl_protocol,query_edge_server,dispatch_task_and_monitor]
tool_node = ToolNode(tools)

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

model_with_tools = ChatOpenAI(
    model="GPT-oss-20b",
    api_key="1756891290237NvNud1IzoEnGtlNncoB1uWl",
    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
    temperature=0.6,
).bind_tools(tools=tools, tool_choice="auto")

def call_model(state: MessagesState):
    messages = state["messages"]
    response = model_with_tools.invoke(messages)

    # ✅ 自动补上缺失的 tool_call_id
    if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
        for tool_call in response.tool_calls:
            if not tool_call.get("id"):
                tool_call["id"] = f"call_{uuid.uuid4().hex[:8]}"

    # return {"messages": [response]}
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
    res = app.invoke(
        {"messages": [{"role": "user", "content": "计算下897*678"}]},
        thread_id="thread-1"
    )
    print(res)
    # print(f"SQLite DB 写入路径：./langgraph_chat.db")