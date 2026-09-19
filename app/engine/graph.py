from langgraph.graph import StateGraph, END, START
from app.engine.state import AgentState
from app.engine.nodes import (
    detect_intent, determine_next_step, retrieve_tools, select_and_extract, 
    validate_tool_call, execute_tool, generate_response
)

def route_after_guardrail(state: AgentState) -> str:
    if not state.get("is_valid_request", True):
        return "generate_response"
    return "determine_next_step"

def route_after_planning(state: AgentState) -> str:
    if state.get("is_complete", False):
        return "generate_response"
    return "retrieve_tools"

def route_after_selection(state: AgentState) -> str:
    if state.get("is_complete", False):
        return "generate_response"
    return "validate_tool_call"

def route_after_validation(state: AgentState) -> str:
    if state.get("validation_error"):
        return "select_and_extract"
    return "execute_tool"

def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("detect_intent", detect_intent)
    workflow.add_node("determine_next_step", determine_next_step)
    workflow.add_node("retrieve_tools", retrieve_tools)
    workflow.add_node("select_and_extract", select_and_extract)
    workflow.add_node("validate_tool_call", validate_tool_call)
    workflow.add_node("execute_tool", execute_tool)
    workflow.add_node("generate_response", generate_response)

    workflow.add_edge(START, "detect_intent")
    
    workflow.add_conditional_edges(
        "detect_intent", route_after_guardrail,
        {"determine_next_step": "determine_next_step", "generate_response": "generate_response"}
    )
    
    workflow.add_conditional_edges(
        "determine_next_step", route_after_planning,
        {"retrieve_tools": "retrieve_tools", "generate_response": "generate_response"}
    )
    
    workflow.add_edge("retrieve_tools", "select_and_extract")
    
    workflow.add_conditional_edges(
        "select_and_extract", route_after_selection,
        {"determine_next_step": "determine_next_step", "validate_tool_call": "validate_tool_call", "generate_response": "generate_response"}
    )
    
    workflow.add_conditional_edges(
        "validate_tool_call", route_after_validation,
        {"select_and_extract": "select_and_extract", "execute_tool": "execute_tool"}
    )
    
    workflow.add_edge("execute_tool", "determine_next_step")
    workflow.add_edge("generate_response", END)
    
    return workflow.compile()
