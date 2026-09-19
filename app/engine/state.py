import operator
from typing import TypedDict, Dict, Any, List, Optional, Annotated

class AgentState(TypedDict):
    """
    The shared memory for the LangGraph agent. 
    Every node reads from and writes updates to this state.
    """
    user_message: str
    
    # Guardrail Results
    is_valid_request: Optional[bool]    # True if request passes security/relevance checks
    rejection_reason: Optional[str]     # Populated if the request is blocked
    
    # Query Decomposition (NEW)
    sub_tasks: Optional[List[str]]
    current_task_index: Optional[int]
    
    # Tool Execution State
    retrieved_tools: List[Dict]         # The narrowed down list of tools from Chroma
    selected_tool_id: Optional[str]     # The specific tool chosen by the LLM
    extracted_params: Dict[str, Any]    # The arguments extracted for the tool
    validation_error: Optional[str]     # If validation fails, store error to feed back to LLM
    
    # Multi-Step Fields
    next_search_query: Optional[str]    # The narrowed sub-task query from the planner
    is_complete: Optional[bool]
    execution_history: Annotated[List[Dict], operator.add]
    
    # Output
    final_response: Optional[str]       # The final human-readable response
