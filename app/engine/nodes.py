import os
import json
import string
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.engine.state import AgentState
from app.core.config import Config

from app.core.llm_setup import extraction_model, embedding_function
from app.execution.validator import SchemaValidator
from app.execution.api_client import APIClient
from app.tools.registry import ToolRegistry
from app.tools.tool_retriever import HybridRetriever
from app.tools.rag_engine import RAGEngine

registry = ToolRegistry()
retriever = HybridRetriever(embedding_function=embedding_function)
rag_engine = RAGEngine(embedding_function=embedding_function)
api_client = APIClient()

class GuardrailResult(BaseModel):
    is_valid: bool = Field(description="True ONLY IF the request is related to finance, APIs, or our system.")
    reason: str = Field(description="Brief reason for your decision.")

class NextStep(BaseModel):
    is_complete: bool = Field(description="True if the user's original request is fully satisfied by the execution history.")
    next_search_query: str = Field(
        description=(
            "A brief NATURAL-LANGUAGE description of the next action needed, in plain English "
            "(e.g. 'create a subscription plan for this product'). "
            "Do NOT guess, invent, or output an API tool ID, function name, or anything in "
            "dotted.snake_case format — you have not seen the real tool IDs yet, and any ID you "
            "make up will be wrong."
        ),
        default=""
    )

class ToolSelection(BaseModel):
    selected_tool_id: str = Field(description="The ID of the tool to execute next.")
    extracted_params: Dict[str, Any] = Field(description="The JSON parameters for the tool. DO NOT hallucinate fake data (e.g. 'New Product'). Use EXACT strings from the user's goal.", default_factory=dict)

def detect_intent(state: AgentState) -> dict:
    structured_guardrail = extraction_model.with_structured_output(GuardrailResult)
    prompt = f"""You are a strict guardrail classifier.
Analyze the user message: '{state['user_message']}'

Is it valid for a Financial Agent? 
VALID tasks: enterprise actions, payments, invoices, audits, subscriptions, creating products/plans.
INVALID tasks: poems, jokes, general chit-chat.

Respond ONLY with a single JSON object matching the requested GuardrailResult schema. DO NOT generate execution plans, arrays, or tools.
Use EXACTLY these keys:
{{
    "is_valid": true,
    "reason": "..."
}}
"""
    result = structured_guardrail.invoke(prompt)
    return {"is_valid_request": result.is_valid, "rejection_reason": result.reason}

def determine_next_step(state: AgentState) -> dict:
    history = state.get("execution_history", [])
    if history:
        last_result = history[-1].get("result", {})
        if isinstance(last_result, dict) and "error" in last_result:
            print("API FAILED. Hard aborting to prevent loop.")
            return {"is_complete": True}

    structured_llm = extraction_model.with_structured_output(NextStep)
    prompt = f"""
    You are the core planner for a FinTech System.
    OVERALL GOAL: "{state['user_message']}"
    EXECUTION HISTORY (What we have already done): {state.get('execution_history', [])}
    
    Have we completely fulfilled the goal? If YES, set 'is_complete' to true.
    If NO, output 'next_search_query' as a short PLAIN-ENGLISH description of the next
    action (e.g. "create a subscription plan for the new product"). Describe the ACTION,
    not a tool name or API endpoint — you have not seen the list of available tools yet,
    so any tool-ID-looking string you produce is a guess and will be wrong.
    
    CRITICAL INSTRUCTION: If the execution history shows that the last step FAILED (e.g., an API error or unauthorized), DO NOT keep retrying the same task indefinitely. Set 'is_complete' to true so we can report the error to the user!
    
    Respond ONLY with a single JSON object matching this EXACT format:
    {{
        "is_complete": false,
        "next_search_query": "..."
    }}
    """
    print("DEBUG: Calling LLM for determine_next_step...")
    result = structured_llm.invoke(prompt)
    print(f"DEBUG: determine_next_step finished. is_complete={result.is_complete}")
    
    next_query = result.next_search_query
    if not next_query or not next_query.strip():
        next_query = state['user_message']
        
    return {"is_complete": result.is_complete, "next_search_query": next_query}

def retrieve_tools(state: AgentState) -> dict:
    if state.get("is_complete"): return {"retrieved_tools": []}
    query = state.get("next_search_query") or state["user_message"]
    top_tool_ids = retriever.search(query, top_k=10)
    retrieved_tools = []
    for tid in top_tool_ids:
        tool = registry.get_tool(tid)
        if tool: retrieved_tools.append({"tool_id": tool.tool_id, "name": tool.name, "description": tool.description, "schema": tool.input_schema})
    return {"retrieved_tools": retrieved_tools}

def select_and_extract(state: AgentState) -> dict:
    print('SELECTING TOOL...')
    print('AVAILABLE:', [t['tool_id'] for t in state['retrieved_tools']])
    if state.get('validation_error'): print('PREV ERROR:', state['validation_error'])
    
    # Loop breaker: if the last 3 history items were validation errors, or the exact same tool 3 times, give up
    history = state.get("execution_history", [])
    if len(history) >= 3:
        last_3 = [str(h.get("result", "")) for h in history[-3:]]
        if all("FAILED" in r for r in last_3):
            print("Validation loop detected. Forcing abort.")
            return {"is_complete": True, "validation_error": None}
            
        last_3_tools = [h.get("tool_id") for h in history[-3:]]
        if len(set(last_3_tools)) == 1:
            print("Execution loop detected (same tool 3 times). Forcing abort.")
            return {"is_complete": True, "validation_error": None}

    import json
    schemas_str = "\n\n".join([f"TOOL ID: {t['tool_id']}\nDESCRIPTION: {t['description']}\nSCHEMA: {json.dumps(t['schema'], indent=2)}" for t in state['retrieved_tools']])
    
    structured_llm = extraction_model.with_structured_output(ToolSelection)
    query = state.get("next_search_query", state["user_message"])
    
    prompt = f"""
    Review the CURRENT GOAL: "{query}" and select EXACTLY ONE tool from the AVAILABLE TOOLS below.
    
    AVAILABLE TOOLS:
    {schemas_str}
    
    EXECUTION HISTORY: {state.get('execution_history', [])}
    
    CRITICAL INSTRUCTION: You are a strict data-extraction bot. You must extract fields explicitly requested in the CURRENT GOAL. For any REQUIRED IDs or references (like product_id or plan_id), you MUST extract them from the results in the EXECUTION HISTORY. Construct a valid JSON object using ONLY the fields you have explicit values for. If the schema contains deeply nested structures, ONLY extract the simple properties you know.
    CRITICAL INSTRUCTION: 'selected_tool_id' MUST be copied EXACTLY, character-for-character, from one of the "TOOL ID:" lines in AVAILABLE TOOLS above. The CURRENT GOAL text is only a description of the task and is NEVER itself a real tool ID — never copy or adapt text from the CURRENT GOAL into 'selected_tool_id'. If nothing in AVAILABLE TOOLS matches, leave 'selected_tool_id' empty instead of guessing.
    CRITICAL INSTRUCTION: DO NOT copy arbitrary output fields (like 'status': 'SUCCESS' or internal 'id' strings) from the EXECUTION HISTORY into the new parameters unless the current tool's schema explicitly requires them as input references (like 'product_id').
    CRITICAL INSTRUCTION: When creating plans or objects with prices/frequencies, YOU MUST translate stated amounts (like '50 USD' or 'monthly') into ALL related schema fields (e.g. 'fixed_price_value', 'interval_unit', 'currency_code', 'interval_count') instead of leaving them blank.
    
    Respond ONLY with a single JSON object matching this EXACT format:
    {{
        "selected_tool_id": "...",
        "extracted_params": {{ ... }}
    }}
    """
    if state.get("validation_error"):
        prompt += f"\nCRITICAL FIX: Your last attempt failed: '{state['validation_error']}'. Fix it."
        
    result = structured_llm.invoke(prompt)
    
    if not result.selected_tool_id or result.selected_tool_id.lower() == "none":
        return {"is_complete": True, "validation_error": None}
        
    return {
        "selected_tool_id": result.selected_tool_id,
        "extracted_params": result.extracted_params,
        "is_complete": False,
        "validation_error": None
    }

def validate_tool_call(state: AgentState) -> dict:
    print('VALIDATING:', repr(state.get('selected_tool_id')))
    tool_id = state.get("selected_tool_id", "")
    current_task = state.get("next_search_query") or state.get("user_message", "")
    
    tool = registry.get_tool(tool_id)
    if not tool:
        valid_ids = [t["tool_id"] for t in state.get("retrieved_tools", [])]
        error = (
            f"'{tool_id}' is not a real tool ID and does not exist. "
            f"You must pick one of these EXACT tool_id values instead: {valid_ids}"
        )
        return {"validation_error": error, "execution_history": [{"task": current_task, "tool_id": tool_id, "params": state.get("extracted_params", {}), "result": "FAILED: Tool ID missing"}]}
    
    params = state.get("extracted_params", {})
    
    # Auto-wrap params into request_body if the schema expects it and the model provided them flat
    if "request_body" in tool.input_schema.get("properties", {}) and "request_body" not in params:
        top_level_keys = set(tool.input_schema["properties"].keys())
        body_params = {}
        for k in list(params.keys()):
            if k not in top_level_keys:
                body_params[k] = params.pop(k)
        params["request_body"] = body_params
            
    # Auto-parse stringified JSON if the model messed up (common with 8B models for JSON Patch arrays)
    if "request_body" in params and isinstance(params["request_body"], str):
        try:
            import json
            params["request_body"] = json.loads(params["request_body"])
        except Exception:
            pass
            
    is_valid, error_msg = SchemaValidator.validate_args(tool, params)
    if not is_valid:
        return {"validation_error": error_msg, "execution_history": [{"task": current_task, "tool_id": tool_id, "params": params, "result": f"FAILED VALIDATION: {error_msg}"}]}
    return {"validation_error": None, "extracted_params": params}

async def execute_tool(state: AgentState) -> dict:
    tool = registry.get_tool(state["selected_tool_id"])
    current_task = state.get("next_search_query", state["user_message"])

    if tool.tool_id == "knowledge.rag_search":
        docs = rag_engine.search(state["extracted_params"]["search_query"])
        return {"execution_history": [{"task": current_task, "tool_id": tool.tool_id, "params": state["extracted_params"], "result": {"retrieved_context": docs}}]}
        
    audit_file = Config.AUDIT_LOG_FILE
    if tool.tool_id == "system.audit_logs":
        if os.path.exists(audit_file):
            with open(audit_file, "r") as f:
                logs = json.load(f)
            return {"execution_history": [{"task": current_task, "tool_id": tool.tool_id, "params": state["extracted_params"], "result": {"status": "success", "recent_logs": logs[-5:]}}]}
        else:
            return {"execution_history": [{"task": current_task, "tool_id": tool.tool_id, "params": state["extracted_params"], "result": {"status": "success", "recent_logs": "No logs."}}]}
            
    raw_url = getattr(tool, "api_endpoint", "") or Config.MOCK_API_URL
    method = getattr(tool, "http_method", "POST")
    auth_type = getattr(tool, "auth_type", "none")
    
    params = dict(state.get("extracted_params", {}))
    json_body = params.pop("request_body", None)
    
    path_vars = [t[1] for t in string.Formatter().parse(raw_url) if t[1] is not None]
    format_dict = {k: params.get(k, f"{{{k}}}") for k in path_vars}
    url = raw_url.format(**format_dict)
    
    query_params = {k: v for k, v in params.items() if k not in path_vars}
    if method.upper() in ["POST", "PUT", "PATCH"] and json_body is None and query_params:
        json_body = query_params
        query_params = None
        
    if getattr(tool, "payload_template", None) and json_body and isinstance(json_body, dict):
        def reconstruct_payload(obj, flat_args, path=[]):
            if isinstance(obj, dict):
                return {k: reconstruct_payload(v, flat_args, path + [k]) for k, v in obj.items()}
            elif isinstance(obj, list) and obj:
                return [reconstruct_payload(item, flat_args, path) for item in obj]
            else:
                key = path[-1] if path else "value"
                
                # Protect structural array keys that must remain unique or strictly match the template
                if key in ["sequence", "tenure_type", "interval_count"]:
                    return obj
                    
                if len(path) > 1 and key in ["value", "id", "type", "status", "code", "name"]:
                    key = f"{path[-2]}_{key}"
                key_fallback = f"{path[-2]}_{key}" if len(path) > 1 else key
                key_super_fallback = f"{path[-3]}_{key}" if len(path) > 2 else key
                
                if key_super_fallback in flat_args: return flat_args[key_super_fallback]
                if key_fallback in flat_args: return flat_args[key_fallback]
                if key in flat_args: return flat_args[key]
                
                # Evaluate Postman variables for uniqueness
                if isinstance(obj, str):
                    if "{{$timestamp}}" in obj:
                        import time
                        obj = obj.replace("{{$timestamp}}", str(int(time.time() * 1000)))
                    if "{{$guid}}" in obj:
                        import uuid
                        obj = obj.replace("{{$guid}}", str(uuid.uuid4()))
                    if "{{$randomInt}}" in obj:
                        import random
                        obj = obj.replace("{{$randomInt}}", str(random.randint(1000, 9999)))
                return obj
        
        json_body = reconstruct_payload(tool.payload_template, json_body)
        
    def resolve_postman_vars(obj):
        if isinstance(obj, dict): return {k: resolve_postman_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list): return [resolve_postman_vars(item) for item in obj]
        elif isinstance(obj, str):
            if "{{$timestamp}}" in obj:
                import time
                obj = obj.replace("{{$timestamp}}", str(int(time.time() * 1000)))
            if "{{$guid}}" in obj:
                import uuid
                obj = obj.replace("{{$guid}}", str(uuid.uuid4()))
            if "{{$randomInt}}" in obj:
                import random
                obj = obj.replace("{{$randomInt}}", str(random.randint(1000, 9999)))
            return obj
        return obj

    json_body = resolve_postman_vars(json_body)
    query_params = resolve_postman_vars(query_params)
        
    result = await api_client.execute_call(url=url, method=method, auth_type=auth_type, query_params=query_params, json_body=json_body)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool_id": tool.tool_id,
        "url": url,
        "method": method,
        "params": state["extracted_params"],
        "status": "SUCCESS" if not result.get("error") else "FAILED"
    }
    
    logs = []
    if os.path.exists(audit_file):
        try:
            with open(audit_file, "r") as f:
                logs = json.load(f)
        except:
            pass
    logs.append(log_entry)
    with open(audit_file, "w") as f:
        json.dump(logs, f, indent=2)
        
    # Streamline the result for the LLM execution history to prevent context overflow and looping
    history_result = {}
    if isinstance(result, dict):
        if "error" in result:
            history_result["error"] = result["error"]
        else:
            history_result["status"] = "SUCCESS"
            # Extract common IDs and references the LLM might need for the next step
            for k in ["id", "name", "status", "product_id", "plan_id", "token"]:
                if k in result:
                    history_result[k] = result[k]
    else:
        history_result = {"status": "SUCCESS", "response": str(result)[:200]}
        
    return {"execution_history": [{"task": current_task, "tool_id": tool.tool_id, "params": state["extracted_params"], "result": history_result}]}

def generate_response(state: AgentState) -> dict:
    if not state.get("is_valid_request", True):
        return {"final_response": '<div class="execution-step"><div class="step-header"><span class="platform-badge" style="background:rgba(239,68,68,0.1);color:#ef4444;">SYSTEM</span><span class="status-badge error">Rejected</span></div><div class="detail-row"><span class="label">Reason</span><span class="value">Request not supported.</span></div></div>'}
        
    history = state.get('execution_history', [])
    include_sub_task = len(history) > 1
    final_html = ""
    
    for item in history:
        task = item.get("task", "")
        tool_id = item.get("tool_id", "")
        params = item.get("params", {})
        result = item.get("result", "")
        
        params_str = json.dumps(params).replace('<', '&lt;').replace('>', '&gt;')
        task_str = str(task).replace('<', '&lt;').replace('>', '&gt;')
        
        sub_task_html = f'<div class="detail-row"><span class="label">Task</span><span class="value">{task_str}</span></div>' if include_sub_task else ""
        
        if tool_id == "knowledge.rag_search":
            answer = extraction_model.invoke(f"Answer briefly using: {result}").content.strip().replace('<', '&lt;').replace('>', '&gt;')
            final_html += f'<div class="execution-step"><div class="step-header"><span class="platform-badge">KNOWLEDGE BASE</span><span class="status-badge">Success</span></div>{sub_task_html}<div class="detail-row"><span class="label">Query</span><span class="value">{params.get("search_query", "")}</span></div><div class="rag-answer">{answer}</div></div>'
        elif tool_id == "system.audit_logs":
            summary = extraction_model.invoke(f"Summarize logs: {result}").content.strip().replace('<', '&lt;').replace('>', '&gt;')
            final_html += f'<div class="execution-step"><div class="step-header"><span class="platform-badge">AUDIT LOGS</span><span class="status-badge">Success</span></div>{sub_task_html}<div class="detail-row"><span class="label">Result</span><span class="value">{summary}</span></div></div>'
        else:
            integration = tool_id.split('.')[0].replace('_', ' ').upper()
            if isinstance(result, dict) and "error" in result:
                status_html = '<span class="status-badge error">Failed</span>'
            elif isinstance(result, str) and "FAIL" in result.upper():
                status_html = '<span class="status-badge error">Failed</span>'
            else:
                status_html = '<span class="status-badge">Success</span>'
                
            final_html += f'<div class="execution-step"><div class="step-header"><span class="platform-badge">{integration}</span>{status_html}</div>{sub_task_html}<div class="detail-row"><span class="label">Tool</span><span class="value mono">{tool_id}</span></div><div class="detail-row"><span class="label">Params</span><span class="value mono">{params_str}</span></div></div>'
            
    return {"final_response": final_html.strip()}


