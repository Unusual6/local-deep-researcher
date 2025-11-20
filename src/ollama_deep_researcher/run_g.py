# scripts/run_graph.py
from ollama_deep_researcher.graph1 import app,checkpointer  # 导入你 graph1.py 中定义的 graph 实例
# 注意：如果你的 graph 依赖其他模块（如 MessagesState、工具函数），确保导入路径正确

if __name__ == "__main__":
    # 1. 定义配置（thread_id 用于多线程/会话隔离，按需调整）
    config = {"configurable": {"thread_id": "b59a6cb5-edfd-4058-852a-282b2bb32b4b"}}
    
    # 2. 构造初始输入（必须匹配你的 graph 状态机的输入要求！）
    # 🔴 注意：你的示例中传了 1 作为输入，但根据之前的代码，你的状态机是 MessagesState（需要 "messages" 字段）
    # 这里替换为符合你状态机的初始输入（以你的 MessagesState 为例）
    initial_input = {
        "messages": [
            # 构造 HumanMessage 作为初始输入（需导入对应的类）
            {"type": "human", "content": "计算58*42的结果是多少？"}
        ]
    }
    
    # 3. 手动调用 graph.invoke() 执行状态机
    result = app.invoke(initial_input, config=config)
    
    # 4. 打印结果（查看状态机执行后的最终状态）
    print("状态机执行结果：")
    print(result)
    # 若想单独查看 messages 字段（对话历史+最终响应）
    for msg in result["messages"]:
        print(f"\n{msg.type}: {msg.content}")

    checkpoint = checkpointer.get_tuple(config)
    print("checkpoint",checkpoint)
    checkpoint_id='b59a6cb5-edfd-4058-852a-282b2bb32b4b'