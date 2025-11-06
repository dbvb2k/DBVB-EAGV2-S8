# modules/tools.py

from typing import List, Dict, Optional, Any


def summarize_tools(tools: List[Any]) -> str:
    """
    Generate a string summary of tools for LLM prompt injection.
    Format: "- tool_name: description"
    """
    summaries = []
    for tool in tools:
        # Handle both dict (SSE) and object (stdio) formats
        if isinstance(tool, dict):
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description provided.")
        else:
            name = getattr(tool, "name", "unknown")
            description = getattr(tool, "description", "No description provided.")
        summaries.append(f"- {name}: {description}")
    return "\n".join(summaries)


def filter_tools_by_hint(tools: List[Any], hint: Optional[str] = None) -> List[Any]:
    """
    If tool_hint is provided (e.g., 'search_documents'),
    try to match it exactly or fuzzily with available tool names.
    """
    if not hint:
        return tools

    hint_lower = hint.lower()
    filtered = []
    for tool in tools:
        # Handle both dict (SSE) and object (stdio) formats
        if isinstance(tool, dict):
            tool_name = tool.get("name", "")
        else:
            tool_name = getattr(tool, "name", "")
        
        if hint_lower in tool_name.lower():
            filtered.append(tool)
    
    return filtered if filtered else tools


def get_tool_map(tools: List[Any]) -> Dict[str, Any]:
    """
    Return a dict of tool_name → tool object for fast lookup
    """
    tool_map = {}
    for tool in tools:
        # Handle both dict (SSE) and object (stdio) formats
        if isinstance(tool, dict):
            name = tool.get("name", "unknown")
        else:
            name = getattr(tool, "name", "unknown")
        tool_map[name] = tool
    return tool_map
