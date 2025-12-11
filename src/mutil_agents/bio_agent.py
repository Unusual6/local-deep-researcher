
import uuid
from langchain_core.messages import AIMessage, HumanMessage, AnyMessage,SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END

from langchain.agents import create_agent
from src.mutil_agents.llm_prompt import llm, prompt, elisa_prompt,zuofei_prompt
from src.mutil_agents.tools import cytokine_tool_node,cytokine_tools
from src.mutil_agents.tools import elisa_tools,elisa_tool_nodes
from src.mutil_agents.tools import zuofei_tools,zuofei_tools_nodes
from langgraph.prebuilt import create_react_agent
# from ...mqtt_test.mqtt_client import client
# export PYTHONPATH=/home/pfjial/local-deep-researcher-main


# ---------------------------------------------------------------------
# ------------------------  子图：Cytokine（Level 3） -----------------
# ---------------------------------------------------------------------

def cytokine_agent(state: MessagesState):
    llm_cytokine_agent = llm.bind_tools(tools=cytokine_tools)
    # 限定单个工具调用
    rule_prompt = SystemMessage(content="优先调用工具，一次只能调用一个工具，禁止同时生成多个 tool_calls！")
    enhanced_messages = state["messages"] + [rule_prompt]
    resp = llm_cytokine_agent.invoke(enhanced_messages)
    # 自动补 tool_call_id
    if isinstance(resp, AIMessage) and resp.tool_calls:
        for t in resp.tool_calls:
            if not t.get("id"):
                t["id"] = f"tc_{uuid.uuid4().hex[:6]}"
    state["messages"].append(resp)
    return state

def cytokine_should_continue(state):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END

cyto_graph = StateGraph(MessagesState)
cyto_graph.add_node("agent", cytokine_agent)
cyto_graph.add_node("tools", cytokine_tool_node)
cyto_graph.add_edge(START, "agent")
cyto_graph.add_conditional_edges("agent", cytokine_should_continue, ["tools", END])
cyto_graph.add_edge("tools", "agent")
cytokine_graph = cyto_graph.compile()

# ---------------------------------------------------------------------
# ------------------------  子图：ELISA（Level 3） --------------------
# ---------------------------------------------------------------------

def elisa_agent(state: MessagesState) -> MessagesState:
    # 核心：用 create_react_agent 替代原生 create_agent
    # create_agent.invoke会隐式调用工具，而不走工具节点
    elisa_agent = create_agent(
        model=llm,
        tools=elisa_tools,  # 传入工具列表
        system_prompt=elisa_prompt,
    )
    # 调用 Agent 并返回增量消息（保留原有逻辑）
    agent_output: MessagesState = elisa_agent.invoke(state)
    new_messages: list[AnyMessage] = agent_output["messages"][len(state["messages"]):]
    return {"messages": new_messages}

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

elisa_graph = StateGraph(MessagesState)
elisa_graph.add_node("agent", elisa_agent)
elisa_graph.add_node("tools", elisa_tool_nodes)  # 修正变量名
elisa_graph.add_edge(START, "agent")
# 仅保留条件边：agent → should_continue → tools/END
elisa_graph.add_conditional_edges(
    source="agent",
    path=should_continue,
    path_map={
        "tools": "tools",
        END: END
    }
)
elisa_graph.add_edge("tools", "agent")  # 工具执行后回到 agent，确认是否继续
elisa_graph = elisa_graph.compile()


# ---------------------------------------------------------------------
# ------------------------  子图：ZUOFEI（Level 3） --------------------
# ---------------------------------------------------------------------

def zuofei_agent(state: MessagesState) -> MessagesState:
    zf_agent = create_agent(
        model=llm,
        tools=zuofei_tools,  # 传入工具列表
        system_prompt=zuofei_prompt,
    )
    # 调用 Agent 并返回增量消息（保留原有逻辑）
    agent_output: MessagesState = zf_agent.invoke(state)
    new_messages: list[AnyMessage] = agent_output["messages"][len(state["messages"]):]
    return {"messages": new_messages}

# def connect(state:MessagesState):
#     client.connect()

def should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        # for t in last_message['tool_calls']:
            return "tools"  
    return END

zuofei_graph = StateGraph(MessagesState)
zuofei_graph.add_node("agent", zuofei_agent)
# zuofei_graph.add_node("connect_server", connect)
zuofei_graph.add_node("tools", zuofei_tools_nodes)  # 修正变量名
zuofei_graph.add_edge(START, "agent")
# zuofei_graph.add_edge("agent", "connect_server")
# 仅保留条件边：agent → should_continue → tools/END
zuofei_graph.add_conditional_edges(
    source="agent",
    path=should_continue,
    path_map={
        "tools": "tools",
        END: END
    }
)
zuofei_graph.add_edge("tools", "agent")  # 工具执行后回到 agent，确认是否继续
zuofei_graph = zuofei_graph.compile()


# ---------------------------------------------------------------------
# ------------------------  领域智能体：Bio（Level 2） -----------------
# ---------------------------------------------------------------------

def route_bio_subgraph(state: MessagesState) -> str:
    """修正：从最后一条用户消息（而非智能体消息）提取关键词，避免路由错误"""
    # 找到最后一条用户消息（而非 AIMessage）
    user_msgs = [msg for msg in state["messages"] if msg.type == "human"]
    if not user_msgs:
        return END
    msg = user_msgs[-1].content.lower()
    
    # 路由规则
    if "cytokine" in msg:
        return "cytokine"
    if "elisa" in msg:
        return "elisa"
    if "zuofei" in msg:
        return "zuofei"
    return END


def bio_agent_node(state: MessagesState) -> MessagesState:
    """修正：1. 提取增量Message 2. 仅追加AI生成的消息 3. 适配路由逻辑"""
    bio_agent = create_react_agent(
        model=llm,
        tools=[],  # 无工具时显式传空列表（避免Agent报错）
        prompt = """作为生物智能体，仅做任务解析，选择合适的子图工具执行任务。用一句话描述，不要长篇大论""",
    )
    
    # 1. 调用Agent：返回完整的MessagesState字典
    agent_output_state: MessagesState = bio_agent.invoke(state)
    
    # 2. 提取Agent新增的Message（仅AI生成的那一条，过滤掉原有消息）
    # 原有消息长度：len(state["messages"])，Agent返回的消息长度：len(agent_output_state["messages"])
    new_messages: list[AnyMessage] = agent_output_state["messages"][len(state["messages"]):]
    
    # 3. 构造增量更新的State（仅返回新增的Message，适配add_messages注解）
    # 关键：返回的是{"messages": [AIMessage]}，而非完整State字典
    return {"messages": new_messages}

def summary_node(state: MessagesState) -> MessagesState:
    # if hasattr(state['messages'][-1] ,'tool_call'):
    #     return KeyError
    print("all actions have done!")
    pass


# ---------------------- 构建生物领域主图（无需修改） ----------------------
bio_graph = StateGraph(MessagesState)
bio_graph.add_node("agent", bio_agent_node)
bio_graph.add_node("summary", summary_node) 
bio_graph.add_node("cytokine", cytokine_graph)  # 子图作为节点
bio_graph.add_node("elisa", elisa_graph)        # 子图作为节点
bio_graph.add_node("zuofei", zuofei_graph) 
# 流程路由（确保route_bio_subgraph能解析AI消息中的tool字段）
bio_graph.set_entry_point("agent")
bio_graph.add_conditional_edges(
    source="agent",
    path=route_bio_subgraph,  # 该函数需解析最后一条AIMessage的content（JSON字符串）获取tool
    path_map={
        "cytokine": "cytokine",
        "elisa": "elisa",
        "zuofei":"zuofei",
        END: END
    }
)
bio_graph.add_edge("cytokine", "summary")
bio_graph.add_edge("elisa", "summary")
bio_graph.add_edge("zuofei", "summary")
bio_graph.add_edge("summary", END)
bio_agent = bio_graph.compile()

# ---------------------------------------------------------------------
# -------------------------- 测试执行（无需修改） ----------------------
# ---------------------------------------------------------------------
if __name__ == "__main__":

    cytokine = 's2样品的cytokine实验，包含混合、孵育、测量信号等步骤'
    elisa = "elisa实验做S3的振荡（10分钟）并测量其速率"
    zuofei = "使用zuofei移液工作站，连接服务器并选择程序运行,合理规划动作顺序去调用工具"
    initial_state: MessagesState = {
        "messages": [HumanMessage(content=zuofei)]
    }
    result = bio_agent.invoke(initial_state)

    for m in result["messages"]:
        print(type(m).__name__, ":", m.content)