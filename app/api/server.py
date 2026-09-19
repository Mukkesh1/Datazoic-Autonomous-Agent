import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn

# Import our graph and setup components
from app.core.config import Config
from app.engine.graph import build_graph
from app.engine.nodes import registry, retriever, rag_engine

# Global graph instance
graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executes once when the server starts. 
    Handles the heavy lifting of indexing 500+ tools into memory.
    """
    print("Loading Tool Registry...")
    data_path = Config.MOCK_TOOLS_FILE
    
    if not os.path.exists(data_path):
        print("WARNING: mock_apis.json not found. Did you run generate_mock_tools.py?")
    else:
        registry.load_from_file(data_path)
        
        tools = registry.get_all_tools()
        if retriever.needs_indexing(tools):
            print(f"First-time setup or tool changes detected. Bootstrapping {len(tools)} tools into ChromaDB and BM25...")
            print("Note: In a true production environment, auto-indexing on startup is disabled and handled via CI/CD.")
            retriever.index_tools(tools)
        else:
            print(f"Persistent database found. Skipping embedding generation for {len(tools)} tools.")
            print("Booting instantly...")
            retriever.load_index()
        
    global graph
    print("Compiling LangGraph Workflow...")
    graph = build_graph()
    
    if rag_engine.needs_indexing():
        print("Knowledge base changes detected. Ingesting RAG documents...")
        rag_engine.ingest_documents()
    else:
        print("Knowledge base unchanged. Using persistent RAG index.")
        
    print("Datazoic Agent Server is Ready!")
    yield
    
    print("Shutting down...")

app = FastAPI(lifespan=lifespan, title="Datazoic Scalable Agentic API")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serves the Vanilla JS frontend UI."""
    with open(Config.UI_PATH, "r", encoding="utf-8") as f:
        return f.read()

class ChatRequest(BaseModel):
    message: str
    
class ChatResponse(BaseModel):
    response: str
    executed_tools: Optional[List[str]] = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """The main entry point for user interactions."""
    if not graph:
        raise HTTPException(status_code=500, detail="Graph not initialized.")
        
    try:
        # Initialize the LangGraph state
        initial_state = {"user_message": request.message}
        
        # Execute the workflow
        # Note: We use invoke() here for simplicity, but astream() is better for streaming UI
        final_state = await graph.ainvoke(initial_state, {"recursion_limit": 100})
        
        history = final_state.get("execution_history", [])
        tools_run = [item["tool_id"] for item in history] if history else []
        
        return ChatResponse(
            response=final_state.get("final_response", "No response generated."),
            executed_tools=tools_run
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
