import json
import requests
from typing import TypedDict, List, Optional, Union
from langgraph.graph import Graph, StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

# 定义状态结构
class State(TypedDict):
    """工作流状态"""
    messages: list  # 对话历史
    user_query: str  # 用户原始查询
    intent: Optional[str]  # 识别的意图
    intent_params: dict  # 意图参数
    tool_result: Optional[Union[dict, str]]  # 工具调用结果
    final_response: Optional[str]  # 最终自然语言响应

# 初始化LLM
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

# 1. 意图识别节点
def identify_intent(state: State) -> State:
    """识别用户输入的意图和参数"""
    user_query = state["user_query"]
    
    # 定义意图识别提示
    prompt = PromptTemplate(
        template="""
        分析用户查询，识别其意图和相关参数。
        
        可能的意图包括：
        - "data_query": 查询数据，需要InfluxDB相关参数
        - "send_command": 下发指令，需要EMQX相关参数
        
        对于data_query，可能的参数包括：measurement, field, start_time, end_time, filter等
        对于send_command，可能的参数包括：topic, payload, qos等
        
        用户查询: {user_query}
        
        请返回JSON格式，包含"intent"和"params"字段。如果无法识别意图，intent设为"unknown"。
        """,
        input_variables=["user_query"]
    )
    
    # 构建意图识别链
    intent_chain = prompt | llm | JsonOutputParser()
    
    # 执行意图识别
    result = intent_chain.invoke({"user_query": user_query})
    
    return {
        **state,
        "intent": result.get("intent"),
        "intent_params": result.get("params", {})
    }

# 2. 工具调用节点
class ToolCaller:
    """工具调用类，负责调用InfluxDB和EMQX API"""
    
    def __init__(self):
        # 配置API端点（实际使用时替换为你的API地址）
        self.influxdb_api = "http://localhost:8086/api/v2"
        self.emqx_api = "http://localhost:8081/api/v5"
        self.influxdb_token = "your-influxdb-token"
        self.emqx_api_key = "your-emqx-api-key"
    
    def query_influxdb(self, params: dict) -> dict:
        """调用InfluxDB API查询数据"""
        try:
            headers = {
                "Authorization": f"Token {self.influxdb_token}",
                "Content-Type": "application/json"
            }
            
            # 构建查询参数
            query_params = {
                "org": params.get("org", "default"),
                "query": f'from(bucket:"{params.get("bucket", "default")}") |> range(start: {params.get("start_time", "-1h")})'
            }
            
            # 如果指定了测量值和字段，添加过滤条件
            if "measurement" in params:
                query_params["query"] += f' |> filter(fn: (r) => r._measurement == "{params["measurement"]}")'
            if "field" in params:
                query_params["query"] += f' |> filter(fn: (r) => r._field == "{params["field"]}")'
            
            response = requests.get(
                f"{self.influxdb_api}/query",
                headers=headers,
                params=query_params
            )
            
            return {
                "status": "success",
                "data": response.json(),
                "message": "数据查询成功"
            }
        except Exception as e:
            return {
                "status": "error",
                "data": None,
                "message": f"查询失败: {str(e)}"
            }
    
    def send_command(self, params: dict) -> dict:
        """通过EMQX API发布指令到指定主题"""
        try:
            if not all(k in params for k in ["topic", "payload"]):
                return {
                    "status": "error",
                    "data": None,
                    "message": "缺少必要参数: topic和payload是必需的"
                }
            
            headers = {
                "Authorization": f"Bearer {self.emqx_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "topic": params["topic"],
                "payload": params["payload"],
                "qos": params.get("qos", 0),
                "retain": params.get("retain", False)
            }
            
            response = requests.post(
                f"{self.emqx_api}/mqtt/publish",
                headers=headers,
                json=payload
            )
            
            return {
                "status": "success" if response.status_code == 200 else "error",
                "data": response.json(),
                "message": "指令发布成功" if response.status_code == 200 else f"发布失败: {response.text}"
            }
        except Exception as e:
            return {
                "status": "error",
                "data": None,
                "message": f"发布失败: {str(e)}"
            }

def call_tool(state: State) -> State:
    """根据识别的意图调用相应的工具"""
    intent = state["intent"]
    params = state["intent_params"]
    tool_caller = ToolCaller()
    
    if intent == "data_query":
        result = tool_caller.query_influxdb(params)
    elif intent == "send_command":
        result = tool_caller.send_command(params)
    else:
        result = {
            "status": "error",
            "message": f"无法识别的意图: {intent}"
        }
    
    return {** state, "tool_result": result}

# 3. 结果生成节点
def generate_response(state: State) -> State:
    """将工具返回的结果转换为自然语言响应"""
    intent = state["intent"]
    tool_result = state["tool_result"]
    user_query = state["user_query"]
    
    # 定义结果生成提示
    prompt = PromptTemplate(
        template="""
        将工具调用结果转换为自然语言回答，确保回答清晰易懂。
        
        用户查询: {user_query}
        意图: {intent}
        工具返回结果: {tool_result}
        
        请用自然语言总结结果，不要使用技术术语，保持口语化。
        如果结果包含错误信息，请清晰地传达错误原因。
        """,
        input_variables=["user_query", "intent", "tool_result"]
    )
    
    # 构建结果生成链
    response_chain = prompt | llm
    
    # 生成自然语言响应
    response = response_chain.invoke({
        "user_query": user_query,
        "intent": intent,
        "tool_result": json.dumps(tool_result)
    })
    
    return {** state, "final_response": response.content}

# 条件判断：是否需要调用工具
def should_call_tool(state: State) -> str:
    """根据意图决定是否调用工具"""
    intent = state["intent"]
    if intent in ["data_query", "send_command"]:
        return "call_tool"
    return "generate_response"

# 构建工作流
def create_workflow() -> Graph:
    """创建并返回完整的LangGraph工作流"""
    workflow = StateGraph(State)
    
    # 添加节点
    workflow.add_node("identify_intent", identify_intent)
    workflow.add_node("call_tool", call_tool)
    workflow.add_node("generate_response", generate_response)
    
    # 定义边
    workflow.add_edge(START, "identify_intent")
    workflow.add_conditional_edges(
        "identify_intent",
        should_call_tool,
        {
            "call_tool": "call_tool",
            "generate_response": "generate_response"
        }
    )
    workflow.add_edge("call_tool", "generate_response")
    workflow.add_edge("generate_response", END)
    
    # 编译工作流
    return workflow.compile()

# 使用示例
if __name__ == "__main__":
    # 创建工作流
    app = create_workflow()
    
    # 示例1: 数据查询
    print("示例1: 数据查询")
    result = app.invoke({
        "user_query": "查询过去24小时内温度传感器的平均温度",
        "messages": []
    })
    print("最终回答:", result["final_response"])
    print("\n" + "="*50 + "\n")
    
    # 示例2: 指令下发
    print("示例2: 指令下发")
    result = app.invoke({
        "user_query": "向主题device/control发送指令，打开设备电源",
        "messages": []
    })
    print("最终回答:", result["final_response"])
    