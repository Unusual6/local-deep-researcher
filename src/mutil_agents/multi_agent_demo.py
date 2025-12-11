import uuid,os
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from IPython.display import Image,display
# ---------------------------------------------------------------------
# ------------------------  LLM and prompt for fields ----------------------------
# ---------------------------------------------------------------------
llm = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1
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

@tool
def chem_tool1(sample: str):
    """模拟工具：测量化学信号"""
    return f"[TOOL] Signal measured for sample {sample}"

cytokine_tools = [mix_reagent, incubate, measure_signal]
cytokine_tool_node = ToolNode(cytokine_tools)

chem_tools = [chem_tool1]
chem_tools_node = ToolNode([chem_tool1])
# ---------------------------------------------------------------------
# ------------------------  子图：Cytokine（Level 3） -----------------
# ---------------------------------------------------------------------



def cytokine_agent(state: MessagesState):
    llm_bio_cytokine_agent = llm.bind_tools(tools=cytokine_tools)
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
    resp = llm.invoke(state["messages"])
    state["messages"].append(resp)
    return state

elisa_graph = StateGraph(MessagesState)
elisa_graph.add_node("agent", elisa_agent)
elisa_graph.add_edge(START, "agent")
elisa_graph = elisa_graph.compile()

# ---------------------------------------------------------------------
# ------------------------  领域智能体：Bio（Level 2） -----------------
# ---------------------------------------------------------------------

def route_bio_subgraph(state):
    msg = state["messages"][-1].content.lower()
    if "cytokine" in msg:
        return "cytokine"
    if "elisa" in msg:
        return "elisa"
    return END

def bio_agent_node(state):
    resp = AIMessage(content="[Bio Agent] Received task but no subgraphs defined.")
    state["messages"].append(resp)
    return state

def bio_should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "chem_tools"
    return END

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
# ------------------------  领域智能体：Chem（Level 2） ---------------
# ---------------------------------------------------------------------

def chem_agent_node(state):
    resp = AIMessage(content="[Chem Agent] Received task but no subgraphs defined.")
    state["messages"].append(resp)
    return state

def chem_should_continue(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "chem_tools"
    return END

chem_graph = StateGraph(MessagesState)
chem_graph.add_node("agent", chem_agent_node)
chem_graph.add_node("chem_tools", chem_tools_node)

chem_graph.add_edge(START, "agent")
chem_graph.add_conditional_edges("agent", chem_should_continue, ["chem_tools", END])
chem_graph.add_edge("chem_tools", "agent")
chem_agent = chem_graph.compile()

# ---------------------------------------------------------------------
# ------------------------  主智能体：Commander（Level 1） ------------
# ---------------------------------------------------------------------

def commander_node(state):
    msg = state["messages"][-1].content.lower()

    if "cytokine" in msg:
        return {"messages":[AIMessage(content='{"agent":"bio","subgraph":"cytokine"}')]}

    if "elisa" in msg:
        return {"messages":[AIMessage(content='{"agent":"bio","subgraph":"elisa"}')]}

    return {"messages":[AIMessage(content='{"agent":"chem","subgraph":"default"}')]}

def route_commander(state):
    content = state["messages"][-1].content
    if '"agent":"bio"' in content:
        return "bio_agent"
    if '"agent":"chem"' in content:
        return "chem_agent"
    return END

main = StateGraph(MessagesState)
main.add_node("commander", commander_node)
main.add_node("bio_agent", bio_agent)
main.add_node("chem_agent", chem_agent)
main.add_edge(START, "commander")
main.add_conditional_edges("commander", route_commander,
                           ["bio_agent", "chem_agent"])
main_app = main.compile()
display(Image(main_app.get_graph().draw_mermaid_png()))
# ---------------------------------------------------------------------
# -------------------------- 测试执行 --------------------------------
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("\n========== 测试：输入任务 “做一个 Cytokine 实验” ==========\n")

    result = main_app.invoke({
        "messages": [
            HumanMessage(content="必须调用对应工具，请做一个 Cytokine 实验，混合 BSA，再孵育 10 分钟，然后测量信号。")
        ]
    })

    for m in result["messages"]:
        print(type(m).__name__, ":", m.content)
