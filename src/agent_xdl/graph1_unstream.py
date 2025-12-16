import uuid,json,os
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import AIMessage,ToolMessage
from src.agent_xdl.tools import llm_calculator_tool,generate_xdl_protocol
# from ollama_deep_researcher.tools import query_edge_server,dispatch_task_and_monitor
# from langgraph.checkpoint.sqlite import SqliteSaver


tools = [llm_calculator_tool,generate_xdl_protocol]
tool_node = ToolNode(tools)

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

model_with_tools = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1
    ).bind_tools(tools=tools)

def call_model(state: MessagesState):
    prompt =  [{"role": "human", "content": "优先调用工具"}]
    
    messages = state["messages"]
    response = model_with_tools.invoke(messages)

    # ✅ 自动补上缺失的 tool_call_id
    if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
        print("+++++++++++++++++++ ")
        for tool_call in response.tool_calls:
            if not tool_call.get("id"):
                tool_call["id"] = f"call_{uuid.uuid4().hex[:8]}"


    if isinstance(response, AIMessage) and isinstance(messages[-1], ToolMessage):
        content_dict  = json.loads(messages[-1].content)
        xdl_protocol = content_dict['xdl_protocol'] 
        print("==="*20)
        print(xdl_protocol)
        first = uuid.uuid4().hex[:8]
        second = uuid.uuid4().hex[:8]
        state["messages"].append(AIMessage(content=json.dumps({
                "blocks":[ {
                    "title": "",
                    "block_id": first,
                    "content": {
                        "text": "标题名称",
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
                        "text": xdl_protocol,
                        "tag": "SIMPLE"
                    },
                    "content_type": "foldable_markdown",
                    "position_type": "left",
                    "stream_mode": "updates",
                    "parent": first,
                    "right": ""
                }],
                "status":'done'
            })))
        return state
    
    return {"messages": [response]}
# checkpointer = SqliteSaver.from_conn_string(
#     "file:./langgraph_chat.db?mode=rwc"
# )

graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
graph = graph.compile()
# app = graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    res = graph.invoke(
        {"messages": [{"role": "human", "content": "合成氧化锆的混合前驱体阶段，生成实验步骤中的核心动作以混合为主的xdl"}]}
    )
    print("=="*40)
    # print(res)
    # print(f"SQLite DB 写入路径：./langgraph_chat.db")