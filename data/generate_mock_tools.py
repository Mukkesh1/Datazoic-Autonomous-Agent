import json
import random
import os

def generate_tools():
    tools = []
    
    # 1. The "Golden" Tools (Including our new RAG and System tools)
    tools.append({
        "tool_id": "paypal.invoicing.send",
        "name": "create_and_send_invoice",
        "description": "Creates an invoice for a specified recipient and amount, then immediately sends it via email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient_email": {"type": "string", "format": "email", "description": "The email address to send the invoice to."},
                "amount": {"type": "number", "description": "The numerical amount for the invoice (e.g., 300)."},
                "currency": {"type": "string", "enum": ["USD", "EUR"], "description": "The currency code, either USD or EUR."}
            },
            "required": ["recipient_email", "amount", "currency"]
        },
        "is_mutating": True,
        "requires_confirmation": True,
        "tags": ["invoice", "billing", "paypal"]
    })
    
    # RAG TOOL (Knowledge Base)
    tools.append({
        "tool_id": "knowledge.rag_search",
        "name": "rag_knowledge_search",
        "description": "Queries the internal knowledge base for rules, policies, fees, and documentation. Use this FIRST if the user asks for a standard rate or policy rule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_query": {"type": "string", "description": "The specific question to ask the knowledge base"}
            },
            "required": ["search_query"]
        },
        "is_mutating": False,
        "requires_confirmation": False,
        "tags": ["docs", "knowledge", "rules", "faq", "policy", "sla", "fee"]
    })
    
    # SYSTEM TOOL (Introspection)
    tools.append({
        "tool_id": "system.audit_logs",
        "name": "system_audit_search",
        "description": "Queries the system audit logs to find the status of previous requests or tool availability.",
        "input_schema": {
            "type": "object",
            "properties": {
                "system_query": {"type": "string"}
            },
            "required": ["system_query"]
        },
        "is_mutating": False,
        "requires_confirmation": False,
        "tags": ["system", "logs", "status", "audit"]
    })
    
    # 2. The "Noise" Tools (To prove the retriever handles scale)
    services = ["stripe", "salesforce", "sap", "internal_crm", "aws", "gcp", "azure"]
    actions = ["get", "update", "delete", "create", "list", "sync"]
    entities = ["user", "invoice", "payment", "dispute", "refund", "report", "database"]
    
    for i in range(500):
        svc = random.choice(services)
        act = random.choice(actions)
        ent = random.choice(entities)
        
        tools.append({
            "tool_id": f"{svc}.{ent}.{act}.v{random.randint(1,3)}",
            "name": f"{act}_{ent}_{svc}",
            "description": f"Executes the '{act}' operation on a '{ent}' within the '{svc}' platform.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string", 
                        "description": f"The unique ID string for the {ent} being operated on."
                    }
                },
                "required": ["id"]
            },
            "is_mutating": act in ["update", "delete", "create", "sync"],
            "requires_confirmation": act == "delete",
            "tags": [svc, ent]
        })
        
    os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), "mock_apis.json"), "w") as f:
        json.dump(tools, f, indent=2)

if __name__ == "__main__":
    generate_tools()
