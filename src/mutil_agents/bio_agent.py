import uuid
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

# ---------------------------------------------------------------------
# ------------------------  LLM and prompt for fields ----------------------------
# ---------------------------------------------------------------------

llm_bio = ChatOpenAI(
    model="GPT-oss-20b",
    api_key="1756891290237NvNud1IzoEnGtlNncoB1uWl",
    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
    # temperature=0.6,
)

prompt = f"""You are an expert laboratory assistant. You can help design and execute experiments in the fields of Chemistry and Biology. Use the available tools to perform tasks as needed.
Available tools:
1. mix_reagent(reagent: str): Mix specified reagents.
2. incubate(time_min: int): Incubate samples for a specified time in minutes        """

# ---------------------------------------------------------------------
# ------------------------  工具（Level 4） ----------------------------
# ---------------------------------------------------------------------

@tool
def mix_reagent(reagent: str):
    """模拟工具：混合试剂"""
    return f"[TOOL] Mixed reagent: {reagent}"

@tool
def incubate(time_min: int):
    """模拟工具：孵育"""
    return f"[TOOL] Incubated for {time_min} minutes"

@tool
def measure_signal(sample: str):
    """模拟工具：测量信号"""
    return f"[TOOL] Signal measured for sample {sample}"


cytokine_tools = [mix_reagent, incubate, measure_signal]
cytokine_tool_node = ToolNode(cytokine_tools)

# ---------------------------------------------------------------------
# ------------------------  子图：Cytokine（Level 3） -----------------
# ---------------------------------------------------------------------



def cytokine_agent(state: MessagesState):
    llm_bio_cytokine_agent = llm_bio.bind_tools(tools=cytokine_tools)
    resp = llm_bio_cytokine_agent.invoke(state["messages"])
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

def elisa_agent(state: MessagesState):
    resp = llm_bio.invoke(state["messages"])
    state["messages"].append(resp)
    return state

elisa_graph = StateGraph(MessagesState)
elisa_graph.add_node("agent", elisa_agent)
elisa_graph.add_edge(START, "agent")
elisa_graph.add_edge("agent", END)
elisa_graph = elisa_graph.compile()

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
    return END

def bio_agent_node(state: MessagesState) -> MessagesState:
    """修正：领域智能体仅做任务解析，不生成无意义消息（避免干扰路由）"""
    # 可选：添加领域智能体的任务解析逻辑（如生成子图执行提示）
    resp = AIMessage(content="[Bio Agent] Task parsed, routing to subgraph...")
    return MessagesState(messages=state.messages + [resp])

# ---------------------- 构建生物领域主图 ----------------------
bio_graph = StateGraph(MessagesState)
bio_graph.add_node("agent", bio_agent_node)
bio_graph.add_node("cytokine", cytokine_graph)  # 子图作为节点
bio_graph.add_node("elisa", elisa_graph)        # 子图作为节点

# 流程路由
bio_graph.set_entry_point("agent")  # 入口：领域智能体
bio_graph.add_conditional_edges(
    source="agent",
    path=route_bio_subgraph,
    path_map={
        "cytokine": "cytokine",
        "elisa": "elisa",
        END: END
    }
)
bio_graph.add_edge("cytokine", END)
bio_graph.add_edge("elisa", END)
bio_agent = bio_graph.compile()


# ---------------------------------------------------------------------
# -------------------------- 测试执行 --------------------------------
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("\n========== 测试：输入任务 “做一个 Cytokine 实验” ==========\n")

    result = bio_agent.invoke({
        "messages": [
            HumanMessage(content="必须调用对应工具，请做一个 Cytokine 实验，混合 BSA，再孵育 10 分钟，然后测量信号。")
        ]
    })

    for m in result["messages"]:
        print(type(m).__name__, ":", m.content)
