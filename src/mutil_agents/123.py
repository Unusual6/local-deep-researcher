# 修复导入 + 补全缺失依赖
from typing import TypedDict, Annotated, List
import operator
from loguru import logger  # 修正 logger 导入（不是直接 import logger）
from langgraph.graph import StateGraph, START, END

# 1. 定义全局程序列表（可替换为从MQTT/设备获取的动态列表）
PROGRAM_LIST = ["Program_001", "Program_002", "Program_003", "Program_004"]

# 2. 定义状态（核心：存储流程数据）
class AgentState(TypedDict):
    program_list: List[str]
    selected_program_idx: int | None
    messages: Annotated[List[dict], operator.add]  # 支持消息追加

# 3. 提示用户选择程序的节点（向Studio展示可选列表）
def prompt_program_choice(state: AgentState) -> AgentState:
    # 拼接可选程序列表（格式化为易读的字符串）
    program_options = "\n".join([
        f"{idx}: {prog}" for idx, prog in enumerate(PROGRAM_LIST)
    ])
    prompt_msg = {
        "role": "system",
        "content": f"""
======= 请选择要执行的程序 =======
{program_options}
请在 LangGraph Studio 的「State」面板中更新 `selected_program_idx` 字段为目标数字！
        """
    }
    return {
        "messages": [prompt_msg],
        "selected_program_idx": None  # 初始化为未选择
    }

# 4. 自定义人工交互节点（提示用户在Studio输入）
def human_approval_node(state: AgentState) -> AgentState:
    """暂停流程，等待用户在Studio手动更新selected_program_idx"""
    prompt_msg = {
        "role": "human",
        "content": f"""
🔍 等待人工输入程序编号：
- 可选范围：1 ~ {len(PROGRAM_LIST)}
- 操作步骤：
  1. 打开 Studio 右侧「State」面板；
  2. 找到 `selected_program_idx` 字段；
  3. 输入数字（如 2）并点击「Update State」；
  4. 流程将自动继续执行。
        """
    }
    return {
        "messages": state["messages"] + [prompt_msg],  # 追加消息（不覆盖原有）
        "selected_program_idx": state["selected_program_idx"]  # 保留当前输入值
    }

# 5. 检查输入有效性的条件函数（决定流程走向）
def check_human_input(state: AgentState) -> str:
    """判断是否输入有效编号，返回下一个节点名"""
    idx = state["selected_program_idx"]
    prog_list = PROGRAM_LIST
    # 验证逻辑：非空 + 数字范围合法
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(prog_list):
        logger.warning(f"无效输入：selected_program_idx = {idx}，继续等待人工输入")
        return "human_approval"  # 无效 → 回到人工节点
    logger.info(f"有效输入：selected_program_idx = {idx}，准备执行程序")
    return "execute_program"  # 有效 → 执行程序

# 6. 执行选中程序的节点（核心业务逻辑）
def execute_selected_program(state: AgentState) -> AgentState:
    idx = state["selected_program_idx"]
    prog_list = PROGRAM_LIST
    
    # 二次验证（防止流程异常）
    if idx is None or idx < 0 or idx >= len(prog_list):
        error_msg = {
            "role": "error",
            "content": f"编号无效！请输入 0-{len(prog_list)-1} 之间的数字"
        }
        return {"messages": state["messages"] + [error_msg]}
    
    # 执行选中的程序（替换为你的实际业务逻辑，如MQTT调用/设备控制）
    selected_prog = prog_list[idx]
    logger.info(f"🚀 开始执行程序：{selected_prog}")
    # --------------------------
    # 这里写你的程序执行逻辑，示例：
    # from mqtt_test.mqtt_client import client
    # client.publish("device/exec", selected_prog)
    # --------------------------
    
    success_msg = {
        "role": "success",
        "content": f"✅ 程序 {selected_prog} 执行完成！"
    }
    return {"messages": state["messages"] + [success_msg]}

# 7. 构建并编译流程图
def build_graph():
    # 初始化图（绑定状态类型）
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("prompt_choice", prompt_program_choice)       # 展示程序列表
    graph.add_node("human_approval", human_approval_node)        # 等待人工输入
    graph.add_node("execute_program", execute_selected_program)  # 执行程序
    
    # 定义流程边
    graph.add_edge(START, "prompt_choice")  # 开始 → 展示列表
    graph.add_edge("prompt_choice", "human_approval")  # 展示后 → 等待输入
    
    # 条件边：根据输入有效性决定下一步（注意方法名是 add_conditional_edge，不是 add_conditional_edges）
    graph.add_conditional_edges(
        "human_approval",
        check_human_input,  # 条件判断函数
        {
            "human_approval": "human_approval",  # 无效输入 → 继续等待
            "execute_program": "execute_program"  # 有效输入 → 执行程序
        }
    )
    
    graph.add_edge("execute_program", END)  # 执行完成 → 结束
    
    # 编译图（关键：启用状态持久化，支持人工干预）
    graph = graph.compile(
        # persist=True,  # 持久化状态，确保人工更新后能继续
        interrupt_before=["human_approval"]  # 可选：在人工节点前中断，更易控制
    )
    return graph

# 8. 初始化编译后的图（供Studio加载）
graph = build_graph()

# 测试用例（本地运行验证，可选）
if __name__ == "__main__":
    # 初始状态：传入程序列表
    initial_state = {
        "program_list": PROGRAM_LIST,
        "selected_program_idx": None,
        "messages": []
    }
    
    # 第一次运行：展示程序列表 → 进入人工等待
    result = compiled_graph.invoke(initial_state)
    print("=== 第一次运行结果（展示列表）===")
    print("\n".join([msg["content"] for msg in result["messages"]]))
    
    # 模拟用户在Studio更新状态（手动设置selected_program_idx=2）
    updated_state = {
        "program_list": PROGRAM_LIST,
        "selected_program_idx": 2,  # 选择Program_003
        "messages": result["messages"]
    }
    
    # 第二次运行：验证输入并执行程序
    final_result = compiled_graph.invoke(updated_state)
    print("\n=== 最终执行结果 ===")
    print("\n".join([msg["content"] for msg in final_result["messages"]]))