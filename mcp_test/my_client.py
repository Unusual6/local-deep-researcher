import asyncio
from fastmcp import Client

client = Client("http://localhost:8000/mcp")

async def call_tool(name: str):
    async with client:
        result = await client.call_tool("greet", {"name": name})
        list_tools = await client.list_tools()
        print("Available tools:",list_tools)
        # for tool in list_tools.tools:
        #     print(f" - {tool.name}: {tool.description}")
        # # return result.content[0].text
        print(result)


asyncio.run(call_tool("Ford"))