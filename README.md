# Datazoic Agent: Autonomous FinTech API Orchestrator

Datazoic Agent is an autonomous, tool-calling FinTech assistant designed to orchestrate complex, multi-step API workflows. It leverages a robust LangGraph state machine, ChromaDB for hybrid semantic tool retrieval, and dynamic schema parsing to execute deep financial transactions (e.g., PayPal Sandbox integration) purely from natural language.

## Key Features

- **Stateful Tool Chaining:** Built on **LangGraph**, the agent maintains a deterministic cyclical graph (`execution_history`), allowing it to pass outputs (e.g., created Product IDs) as inputs to subsequent tool calls (e.g., Subscription Plans).
- **Hybrid RAG Tool Retrieval:** Instead of injecting hundreds of tools into the LLM context window, it uses **ChromaDB** and a **BM25 keyword index** to dynamically fetch the exact tools required for the user's intent.
- **Dynamic Schema Flattening:** Parses raw Postman collections, flattens deeply nested arrays/objects into Pydantic schemas for the LLM to extract, and recursively reconstructs the nested JSON payload before execution.
- **Autonomous Security:** Intercepts API calls, resolves environment credentials, and securely generates and injects OAuth2 Bearer tokens at execution time.
- **Strict Guardrails & Hard Aborts:** Prevents LLM hallucination loops by explicitly aborting the graph if a remote endpoint returns a `400` or `422` error (e.g., strict KYC validation failures).

## Project Structure

```text
datazoic_agent/
├── .env                      # Environment variables (PayPal keys, LangSmith config)
├── app/                      # Main Application Directory
│   ├── api/                  # FastAPI layer
│   ├── core/                 # Core configuration & LLM initialization
│   ├── engine/               # LangGraph Orchestration & State definitions
│   ├── execution/            # Strict execution guardrails & API Client
│   ├── tools/                # Tooling, Registry, and Hybrid RAG retrieval engine
│   └── static/               # Vanilla HTML/JS Frontend UI
├── data/                     # Persistent Data & Tool Definitions
└── scripts/                  # Offline utilities (ingest_postman.py)
```

## Getting Started

### Prerequisites
- Python 3.12+
- Access to an LLM provider (Ollama for local, or API keys for cloud models)
- PayPal Sandbox Developer Credentials

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/datazoic_agent.git
   cd datazoic_agent
   ```

2. **Set up the virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```ini

   PAYPAL_CLIENT_ID=your_sandbox_client_id
   PAYPAL_SECRET=your_sandbox_secret

   STRONG_LLM_MODEL=gpt-oss:120b-cloud

   # LangSmith Observability (Optional)
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=your_langsmith_key
   LANGCHAIN_PROJECT="LangSmith App Name"
   ```

5. **Run the Application**
   ```bash
   python -m app.api.server
   ```
   The backend and UI will be available at `http://localhost:8000`.

## License
MIT License
