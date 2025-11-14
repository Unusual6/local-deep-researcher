import uuid
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage
from src.ollama_deep_researcher.tools1 import llm_calculator_tool,generate_xdl_protocol
from src.ollama_deep_researcher.tools1 import query_edge_server,dispatch_task_and_monitor

tools = [llm_calculator_tool,generate_xdl_protocol,query_edge_server,dispatch_task_and_monitor]
tool_node = ToolNode(tools)

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

model_with_tools = ChatOpenAI(
    model="Qwen3-32B-FP8",
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

    return {"messages": [response]}

graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
app = graph.compile()


# create_react_graph = graph.create_react_graph()