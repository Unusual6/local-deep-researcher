from langgraph_sdk import get_client
import asyncio

# 连接本地LangGraph API服务器
client = get_client(url="http://localhost:2024")

async def main():
    # 关键修改：参数名从 assistant 改为 assistant_id
    async for chunk in client.runs.stream(
        thread_id='98540376-8a94-4d31-bed5-60890a97bda7',  # 无线程模式
        assistant_id="ollama_deep_researcher",  # 正确参数名 + 合法图形名称
        input={
            "messages": [  # 确保是列表格式（兼容大多数图形输入要求）
                {
                    "role": "human",
                    "content": "add,elisa,heat,and so on"
                }
            ]
        },
        # 旧版SDK可能不支持 stream_mode 参数，若报错可删除该行
        # stream_mode="values"
    ):
        # print(f"接收的数据类型: {chunk.type}")
        # 不同版本 chunk 结构可能不同，调整输出逻辑适配
        if hasattr(chunk, "content"):
            print(f"数据内容: {chunk.content}")
        elif hasattr(chunk, "data"):
            print(f"数据内容: {chunk.data}")
        # 调试用：打印完整chunk结构，方便确认数据格式
        # print(f"完整响应: {chunk}")

if __name__ == "__main__":
    asyncio.run(main())