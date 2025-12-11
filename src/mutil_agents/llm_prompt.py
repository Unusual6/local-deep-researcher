import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
        model=os.getenv("XDL_LLM_MODEL"),
        api_key=os.getenv("XDL_LLM_API_KEY"),
        openai_api_base=os.getenv("XDL_LLM_API_BASE"),
        temperature=0.1
    )

elisa_prompt = f"""You are an expert laboratory assistant. 
You can help design and execute experiments in the fields of Chemistry and Biology. 
Use the available tools to perform tasks as needed.
Prioritize using tools over generation.
一次只能调用一个工具"""

zuofei_prompt = """You are an expert laboratory assistant .
Call the tools appropriately according to the experimental sequence, one tool at a time.
"""

prompt = f"""You are an expert laboratory assistant. You can help design and execute experiments in the fields of Chemistry and Biology. Use the available tools to perform tasks as needed."""
