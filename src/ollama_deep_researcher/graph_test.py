import json

from pydantic import BaseModel, Field
from typing_extensions import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import START, END, StateGraph
from langchain_openai import ChatOpenAI
from langchain.tools import Tool

from ollama_deep_researcher.configuration import Configuration, SearchAPI
from ollama_deep_researcher.utils import (
    deduplicate_and_format_sources,
    tavily_search,
    format_sources,
    perplexity_search,
    duckduckgo_search,
    searxng_search,
    strip_thinking_tokens,
    get_config_value,
)
from ollama_deep_researcher.state import (
    SummaryState,
    SummaryStateInput,
    SummaryStateOutput,
)
from ollama_deep_researcher.prompts import (
    query_writer_instructions,
    summarizer_instructions,
    reflection_instructions,
    get_current_date,
    json_mode_query_instructions,
    tool_calling_query_instructions,
    json_mode_reflection_instructions,
    tool_calling_reflection_instructions,
)
from ollama_deep_researcher.lmstudio import ChatLMStudio

# Constants
MAX_TOKENS_PER_SOURCE = 1000
CHARS_PER_TOKEN = 4

def generate_search_query_with_structured_output(
    configurable: Configuration,
    messages: list,
    tool_class,
    fallback_query: str,
    tool_query_field: str,
    json_query_field: str,
):
    """Helper function to generate search queries using either tool calling or JSON mode.
    
    Args:
        configurable: Configuration object
        messages: List of messages to send to LLM
        tool_class: Tool class for tool calling mode
        fallback_query: Fallback search query if extraction fails
        tool_query_field: Field name in tool args containing the query
        json_query_field: Field name in JSON response containing the query
        
    Returns:
        Dictionary with "search_query" key
    """
    if configurable.use_tool_calling:
        llm = get_llm(configurable).bind_tools([tool_class])
        result = llm.invoke(messages)

        if not result.tool_calls:
            return {"search_query": fallback_query}
        
        try:
            tool_data = result.tool_calls[0]["args"]
            search_query = tool_data.get(tool_query_field)
            return {"search_query": search_query}
        except (IndexError, KeyError):
            return {"search_query": fallback_query}
    
    else:
        # Use JSON mode
        llm = get_llm(configurable)
        result = llm.invoke(messages)
        print(f"result: {result}")
        content = result.content

        try:
            parsed_json = json.loads(content)
            search_query = parsed_json.get(json_query_field)
            if not search_query:
                return {"search_query": fallback_query}
            return {"search_query": search_query}
        except (json.JSONDecodeError, KeyError):
            if configurable.strip_thinking_tokens:
                content = strip_thinking_tokens(content)
            return {"search_query": fallback_query}

def get_llm(configurable: Configuration):
    """Helper function to initialize LLM based on configuration.

    Uses JSON mode if use_tool_calling is False, otherwise regular mode for tool calling.

    Args:
        configurable: Configuration object containing LLM settings

    Returns:
        Configured LLM instance
    """
    if configurable.llm_provider == "lmstudio":
        if configurable.use_tool_calling:
            return ChatLMStudio(
                base_url=configurable.lmstudio_base_url,
                model=configurable.local_llm,
                temperature=0,
            )
        else:
            return ChatLMStudio(
                base_url=configurable.lmstudio_base_url,
                model=configurable.local_llm,
                temperature=0,
                format="json",
            )
    elif configurable.llm_provider == "ollama":  # Default to Ollama
        if configurable.use_tool_calling:
            return ChatOllama(
                base_url=configurable.ollama_base_url,
                model=configurable.local_llm,
                temperature=0,
            )
        else:
            return ChatOllama(
                base_url=configurable.ollama_base_url,
                model=configurable.local_llm,
                temperature=0,
                format="json",
            )
    else:
        if configurable.use_tool_calling:
            return ChatOpenAI(
                    model="Qwen3-32B-FP8",    # 你最初的模型，无需换！
                    api_key="1756891290237NvNud1IzoEnGtlNncoB1uWl",
                    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
                    temperature=0.6,
                    # top_p=0.9,
                    max_tokens=1024,
                )
        else:
            return ChatOpenAI(
                model="Qwen3-32B-FP8",    # 你最初的模型，无需换！
                    api_key="1756891290237NvNud1IzoEnGtlNncoB1uWl",
                    openai_api_base="http://120.204.73.73:8033/api/ai-gateway/v1",
                    temperature=0.6,
                    # top_p=0.9,
                    max_tokens=1024,
                    # format="json",
                )

# Nodes
def generate_query(state: SummaryState, config: RunnableConfig):
    """LangGraph node that generates a search query based on the research topic.

    Uses an LLM to create an optimized search query for web research based on
    the user's research topic. Supports both LMStudio and Ollama as LLM providers.

    Args:
        state: Current graph state containing the research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated query
    """

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date, research_topic=state.research_topic
    )

    # Generate a query
    configurable = Configuration.from_runnable_config(config)

    @tool
    class Query(BaseModel):
        """
        This tool is used to generate a query for web search.
        """

        query: str = Field(description="The actual search query string")
        rationale: str = Field(
            description="Brief explanation of why this query is relevant"
        )

    messages = [
        SystemMessage(
            content=formatted_prompt + (
                tool_calling_query_instructions if configurable.use_tool_calling 
                else json_mode_query_instructions
            )
        ),
        HumanMessage(content="Generate a query for web search:"),
    ]

    return generate_search_query_with_structured_output(
        configurable=configurable,
        messages=messages,
        tool_class=Query,
        fallback_query=f"Tell me more about {state.research_topic}",
        tool_query_field="query",
        json_query_field="query",
    )


def route_research(
    state: SummaryState, config: RunnableConfig
) -> Literal["tools", "END"]:
    """LangGraph routing function that determines the next step in the research flow.

    Controls the research loop by deciding whether to continue gathering information
    or to finalize the summary based on the configured maximum number of research loops.

    Args:
        state: Current graph state containing the research loop count
        config: Configuration for the runnable, including max_web_research_loops setting

    Returns:
        String literal indicating the next node to visit ("web_research" or "finalize_summary")
    """

    configurable = Configuration.from_runnable_config(config)
    if state.research_loop_count <= configurable.max_web_research_loops:
        return "tools"
    else:
        return "END"

from src.ollama_deep_researcher.tools import get_tools

def chat_node(state: SummaryState, config: RunnableConfig):
    state.iteration += 1
    if state.iteration > 5:
        return {"running_summary": result.content, "next_tool": None}

    configurable = Configuration.from_runnable_config(config)
    llm = get_llm(configurable)
    tools = get_tools(llm)
    llm_with_tools = llm.bind_tools(tools)
    result = llm_with_tools.invoke(
        [
            SystemMessage(content="You are a helpful assistant.Use the appropriate tool to deal with this topic."),
            HumanMessage(content=state.research_topic),
        ]
    )
    print("--------------------------------",result)
    # return {"running_summary": result.content}
    if hasattr(result, "tool_calls") and result.tool_calls:
        tool_call = result.tool_calls[0]
        return {
            "running_summary": result.content,
            "next_tool": tool_call["name"],
            "tool_input": tool_call["args"],
        }
    else:
        return {
            "running_summary": result.content,
            "next_tool": None,
        }

def tools_node(state: SummaryState, config):
    configurable = Configuration.from_runnable_config(config)
    llm = get_llm(configurable)
    tools = {t.name: t for t in get_tools(llm)}  # 转成字典方便查找
    tool_name = state.next_tool
    tool_input = state.tool_input

    if not tool_name or tool_name not in tools:
        return {"tool_result": "未找到匹配的工具", "running_summary": state["running_summary"]}

    tool = tools[tool_name]
    # result = tool.run(tool_input)
    # return {"tool_result": result, "running_summary": f"{state['running_summary']}\n[工具执行结果]: {result}"}


    # ✅ 检查工具函数签名
    try:
        if isinstance(tool_input, dict) and len(tool_input) == 1:
            # 例如 {"user_input": "..."} 时取出值
            input_value = list(tool_input.values())[0]
        else:
            input_value = tool_input

        result = tool.run(input_value)
    except Exception as e:
        result = f"[工具执行异常: {e}]"

    return SummaryState(
        research_topic=state.research_topic,
        running_summary=f"{state.running_summary}\n[工具执行结果]: {result}",
        tool_result=result,
        next_tool=None
    )


def route_from_chat(state: SummaryState):
    # 停止条件
    if getattr(state, "iteration", 0) > 5:
        return END

    next_tool = getattr(state, "next_tool", None)
    if next_tool:
        return "tools"
    return END


# Add nodes and edges
builder = StateGraph(
    SummaryState,
    input=SummaryStateInput,
    output=SummaryStateOutput,
    config_schema=Configuration,
)


builder.add_node("chat", chat_node)
builder.add_node("tools", tools_node)

builder.add_edge(START, "chat")
builder.add_conditional_edges("chat", route_from_chat)
builder.add_edge("tools", "chat")
# builder.add_edge("chat", END)
graph = builder.compile()
