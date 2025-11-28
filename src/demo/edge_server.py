# edge_server.py
from fastapi import FastAPI
import uvicorn
import asyncio

app = FastAPI()

# 设备控制端

@app.post("/device/execute")
async def execute_step(payload: dict):
    device = payload["device"]
    step = payload["step"]

    print(f"🛠️ Device {device} executing: {step['step']} ...")

    # 模拟设备执行时间
    await asyncio.sleep(1)

    return {"status": "done", "step": step["step"]}


if __name__ == "__main__":
    print("🚀 Edge server running at 9000 ...")
    uvicorn.run(app, host="0.0.0.0", port=9000)
