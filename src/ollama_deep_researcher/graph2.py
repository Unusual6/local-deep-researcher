import uuid
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

# 导入你的工具（保持不变）
from ollama_deep_researcher.tools import (
    llm_calculator_tool,
    generate_xdl_protocol,
    query_edge_server,
    dispatch_task_and_monitor
)

# LLM 模型配置（保持不变）
model_with_tools = ChatOpenAI(
    model="Qwen3-32B-FP8",
    api_key="1756891290237NvNud1IzoEnGtlNncoB1uWl",
    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
    temperature=0.6,
).bind_tools(tools=[llm_calculator_tool, generate_xdl_protocol, query_edge_server, dispatch_task_and_monitor], tool_choice="auto")

# 节点函数（保持不变）
def call_model(state: MessagesState):
    messages = state["messages"]  # 旧版本：字典式访问
    response = model_with_tools.invoke(messages)
    if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
        for tool_call in response.tool_calls:
            if not tool_call.get("id"):
                tool_call["id"] = f"call_{uuid.uuid4().hex[:8]}"
    return {"messages": [response]}  # 旧版本：返回字典

def should_continue(state: MessagesState):
    messages = state["messages"]  # 旧版本：字典式访问
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

# 工具节点（保持不变）
tools = [llm_calculator_tool, generate_xdl_protocol, query_edge_server, dispatch_task_and_monitor]
tool_node = ToolNode(tools)

# 🔴 核心1：用 with 语句正确获取 SqliteSaver 实例
with SqliteSaver.from_conn_string(
    conn_string="langgraph_chat2.db",
    # timeout=30.0
) as checkpointer:
    # 构建并编译状态机
    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, ["tools", END])
    graph.add_edge("tools", "agent")
    app = graph.compile(checkpointer=checkpointer)
    
    if __name__ == "__main__":
        thread_id = "fb51216b-599b-47a4-92e1-bc75256dc57c"
        config = {"configurable": {"thread_id": thread_id}}
        
        # 测试1：首次对话
        print("=== 测试1：启动新实验（首次对话）===")
        initial_input = {
            "messages": [HumanMessage(content="计算421*82")]
        }
        result1 = app.invoke(initial_input, config=config)  # 旧版本：返回字典
        
        # 🔴 核心2：字典式访问 messages（适配旧版本）
        for msg in result1["messages"]:
            print(f"\n{msg.type.upper()}: {msg.content}")
        
        # 🔴 核心3：通过 checkpointer 查询 checkpoint_id（通用方式）
        latest_checkpoint = checkpointer.get({"configurable": {"thread_id": thread_id}})

        print("latest_checkpoint =", latest_checkpoint)  # 推荐先打印一次确认结构

        if latest_checkpoint:
            checkpoint_id = latest_checkpoint["id"]
            print(f"生成的 checkpoint_id：{checkpoint_id}")
        else:
            print("未生成 checkpoint")

        
        # 测试2：恢复历史对话
        print("\n=== 测试2：恢复历史对话（继续交互）===")
        new_input = {
            "messages": [HumanMessage(content="计算12+5结果加上1000是多少？")]
        }
        result2 = app.invoke(new_input, config=config)  # 旧版本：返回字典
        
        # 🔴 核心4：字典式访问完整历史消息
        print("\n完整对话历史：")
        for i, msg in enumerate(result2["messages"], 1):
            print(f"\n{i}. {msg.type.upper()}: {msg.content}")
        
        # （可选）查询更新后的 checkpoint_id
        latest_checkpoint2 = checkpointer.get({"configurable": {"thread_id": thread_id}})
        if latest_checkpoint2:
            print(f"\n更新后的 checkpoint_id：{latest_checkpoint2["id"]}")