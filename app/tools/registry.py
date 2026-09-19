import json
from typing import Dict, List, Optional
from app.tools.schemas import ToolMetadata

class ToolRegistry:
    """
    In-memory store for all available tools. 
    Loads from a data source and validates against our Pydantic schema.
    """
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}

    def load_from_file(self, file_path: str) -> None:
        """Loads and validates tools from a JSON file."""
        with open(file_path, 'r') as f:
            raw_tools = json.load(f)
        
        for t in raw_tools:
            tool = ToolMetadata(**t) # Pydantic validates the structure instantly
            self._tools[tool.tool_id] = tool
            
    def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        return self._tools.get(tool_id)

    def get_all_tools(self) -> List[ToolMetadata]:
        return list(self._tools.values())
