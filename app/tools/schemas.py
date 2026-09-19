from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Union

class ToolMetadata(BaseModel):
    """
    Defines the strict schema for any tool loaded into our system.
    This guarantees that every tool has the required metadata for routing and safety.
    """
    tool_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]  # The JSON schema defining the arguments the tool expects
    payload_template: Optional[Union[Dict[str, Any], List[Any]]] = None
    
    # Execution & Routing
    api_endpoint: str = ""        # e.g., https://api-m.sandbox.paypal.com/v2/invoicing/invoices
    http_method: str = "POST"     # GET, POST, PUT, DELETE, PATCH
    auth_type: str = "none"       # 'paypal_oauth', 'bearer', 'none'
    
    # Safety & Discovery
    is_mutating: bool = False     # If True, this tool modifies external state
    requires_confirmation: bool = False # If True, triggers the Human-In-The-Loop gate
    tags: List[str] = []          # Keywords for better BM25 retrieval
