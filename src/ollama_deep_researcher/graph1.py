import uuid,os
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage
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
    # res = app.invoke(
    #     {"messages": [{"role": "user", "content": "计算下897*678"}]},
    #     thread_id="thread-1"
    # )
    # print(res)
    print("===="*20)
    for chunk in app.stream(
            {"messages": [{"role": "user", "content": "北京的天气怎么样"}]},
            stream_mode="updates"):
        print(chunk)

    # print(f"SQLite DB 写入路径：./langgraph_chat.db")