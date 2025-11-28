# langgraph_server.py
from fastapi import FastAPI
import uvicorn
import requests
import asyncio
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List, Dict, Any

# -----------------------------
# 1. 定义状态结构
# -----------------------------
class WorkflowState(TypedDict):
    steps: List[Dict[str, Any]]
    current: int
    results: List[str]

# -----------------------------
# 2. 定义执行节点
# -----------------------------
async def dispatch_step(state: WorkflowState):
    idx = state["current"]
    step = state["steps"][idx]

    print(f"➡ Dispatching step {idx+1}: {step}")

    # 调用 edge server
    resp = requests.post(
        "http://127.0.0.1:9000/device/execute",
        json={"device": "ELx405_01", "step": step},
    )
    data = resp.json()

    # 更新结果
    new_results = state["results"] + [data["step"]]

    return {
        "results": new_results,
        "current": idx + 1,
    }

# -----------------------------
# 3. 构建 LangGraph workflow
# -----------------------------
checkpointer = MemorySaver()
builder = StateGraph(WorkflowState)

builder.add_node("dispatch_step", dispatch_step)
builder.set_entry_point("dispatch_step")

# step 循环
builder.add_conditional_edges(
    "dispatch_step",
    lambda s: "dispatch_step" if s["current"] < len(s["steps"]) else END,
    {
        "dispatch_step": "dispatch_step",
        END: END,
    }
)

graph = builder.compile()

# -----------------------------
# 4. FastAPI 暴露 /run
# -----------------------------
app = FastAPI()

@app.post("/run")
async def run_workflow():
    print("🚀 Starting workflow...")

    initial_state = {
        "steps": [
            {"step": "prime"},
            {"step": "wash"},
            {"step": "read_signal"},
        ],
        "current": 0,
        "results": [],
    }

    # 🔥 LangGraph 要求的正确 config
    config = {"configurable": {"thread_id": "xyz"}}

    final_state = None

    # 🔥 修复：必须带 config，必须带 async streaming
    async for event in graph.astream(initial_state, config):
        final_state = event

    return {"workflow_result": final_state}


if __name__ == "__main__":
    print("🚀 LangGraph server at 8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
