from typing import Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
import sqlite3
import uuid
import time
import json

# ========== 1. SQLite 初始化（内置数据库，无需安装） ==========
def init_sqlite():
    """创建 SQLite 数据库和状态表（首次运行自动创建）"""
    conn = sqlite3.connect("experiment_state.db")  # 数据库文件：experiment_state.db
    cursor = conn.cursor()
    # 创建状态表：存储实验ID和序列化后的状态
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiment_states (
            experiment_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# 初始化数据库（程序启动时执行一次）
init_sqlite()

# ========== 2. 状态模型 ==========
class ExperimentState(BaseModel):
    experiment_id: str  # 实验唯一ID
    progress: int = 0  # 进度（0-100）
    is_success: Optional[bool] = None  # 是否成功
    result: Optional[str] = None  # 实验结果

# ========== 3. 持久化工具函数（SQLite 替代 Redis） ==========
def save_state(state: ExperimentState):
    """保存状态到 SQLite 数据库"""
    try:
        conn = sqlite3.connect("experiment_state.db")
        cursor = conn.cursor()
        # 序列化状态为 JSON 字符串
        state_json = state.model_dump_json()
        # 插入或更新状态（存在则更新，不存在则插入）
        cursor.execute('''
            INSERT OR REPLACE INTO experiment_states (experiment_id, state_json)
            VALUES (?, ?)
        ''', (state.experiment_id, state_json))
        conn.commit()
        conn.close()
        print(f"[持久化] 保存状态到 SQLite（实验ID：{state.experiment_id}，进度：{state.progress}%）")
    except Exception as e:
        print(f"[持久化失败] {str(e)}")

def load_state(experiment_id: str) -> Optional[ExperimentState]:
    """从 SQLite 加载状态"""
    try:
        conn = sqlite3.connect("experiment_state.db")
        cursor = conn.cursor()
        # 查询状态
        cursor.execute('''
            SELECT state_json FROM experiment_states WHERE experiment_id = ?
        ''', (experiment_id,))
        result = cursor.fetchone()
        conn.close()
        if not result:
            print(f"[加载失败] 无实验 {experiment_id} 的状态")
            return None
        # JSON 字符串转 Pydantic 模型
        return ExperimentState.model_validate_json(result[0])
    except Exception as e:
        print(f"[加载失败] {str(e)}")
        return None

# ========== 4. 节点装饰器（持久化逻辑不变） ==========
def with_persistence(node_func):
    def wrapper(state: ExperimentState) -> ExperimentState:
        # 执行前加载状态
        if state.experiment_id:
            loaded_state = load_state(state.experiment_id)
            if loaded_state:
                state = loaded_state
                print(f"[装饰器] 加载到最新状态：进度 {state.progress}%")
        
        # 执行节点逻辑
        updated_state = node_func(state)
        
        # 执行后保存状态
        save_state(updated_state)
        return updated_state
    return wrapper

# ========== 5. 节点函数 ==========
@with_persistence
def init_experiment(state: ExperimentState) -> ExperimentState:
    if not state.experiment_id:
        state.experiment_id = f"exp_{uuid.uuid4().hex[:6]}"
    state.progress = 0
    print(f"[初始化] 实验ID：{state.experiment_id}，进度：{state.progress}%")
    return state

@with_persistence
def run_experiment(state: ExperimentState) -> ExperimentState:
    print(f"[执行实验] {state.experiment_id} 开始运行...")
    start_step = state.progress // 33  # 从当前进度继续
    for i in range(start_step, 3):
        time.sleep(1)
        state.progress = (i + 1) * 33
        print(f"[执行实验] 进度：{state.progress}%")
    state.is_success = True
    state.result = "data collection is done!"
    print(f"[执行实验] {state.experiment_id} 完成！")
    return state

@with_persistence
def finish_experiment(state: ExperimentState) -> ExperimentState:
    print(f"[完成] 实验 {state.experiment_id} 流程结束")
    return state

# ========== 6. 构建 LangGraph 工作流 ==========
workflow = StateGraph(ExperimentState)
workflow.add_node("init", init_experiment)
workflow.add_node("run", run_experiment)
workflow.add_node("finish", finish_experiment)
workflow.set_entry_point("init")
workflow.add_edge("init", "run")
workflow.add_edge("run", "finish")
workflow.add_edge("finish", END)
app = workflow.compile()  # 无 middleware，兼容旧版 LangGraph

# ========== 7. 测试运行/断点续跑（核心修复：字典转模型） ==========
def run_or_resume(experiment_id: Optional[str] = None):
    if experiment_id:
        loaded_state = load_state(experiment_id)
        if not loaded_state:
            print("无此实验状态，启动新实验...")
            loaded_state = ExperimentState(experiment_id="")
    else:
        loaded_state = ExperimentState(experiment_id="")
    
    # 执行流程（旧版 LangGraph 返回 dict，需转为模型）
    result_dict = app.invoke(loaded_state.dict())  # 传入字典，返回字典
    # 字典转 Pydantic 模型（关键修复）
    result = ExperimentState.model_validate(result_dict)
    
    print(f"\n最终结果：实验 {result.experiment_id} → {'成功' if result.is_success else '失败'}")
    return result.experiment_id

# 测试1：启动新实验（直接运行，无需任何外部服务）
print("=== 测试1：启动新实验 ===")
exp_id = run_or_resume()  # 输出实验ID，如 exp_a1b2c3

# 测试2：断点续跑（先终止测试1，再执行）
# print("\n=== 测试2：断点续跑 ===")
# run_or_resume(experiment_id=exp_id)  # 传入上一步的实验ID