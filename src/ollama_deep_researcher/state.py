import operator
from dataclasses import dataclass, field
from typing_extensions import Annotated


@dataclass(kw_only=True)
class SummaryState:
    research_topic: str = field(default=None)  # Report topic
    search_query: str = field(default=None)  # Search query
    web_research_results: Annotated[list, operator.add] = field(default_factory=list)
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list)
    research_loop_count: int = field(default=0)  # Research loop count
    running_summary: str = field(default=None)  # Final report
    next_tool: str = field(default=None)
    tool_input: dict = field(default_factory=dict)
    tool_result: dict = field(default_factory=dict)
    iteration: int = 0


@dataclass(kw_only=True)
class SummaryStateInput:
    research_topic: str = field(default=None)  # Report topic


@dataclass(kw_only=True)
class SummaryStateOutput:
    running_summary: str = field(default=None)  # Final report
