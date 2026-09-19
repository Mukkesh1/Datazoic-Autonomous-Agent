import os
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()

class Config:
    """Central configuration for the Agent."""
    
    # 1. Models
    STRONG_LLM_MODEL = os.getenv("STRONG_LLM_MODEL", "llama3.1") 
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    
    # 2. Project Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    UI_PATH = os.path.join(BASE_DIR, "app", "static", "index.html")
    
    MOCK_TOOLS_FILE = os.path.join(DATA_DIR, "paypal_tools.json")
    AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_logs.json")
    
    # Vector DB & RAG Paths
    CHROMA_DB_DIR = os.path.join(DATA_DIR, "vector_db")
    KB_DIR = os.path.join(DATA_DIR, "knowledge_base")
    BM25_INDEX_FILE = os.path.join(DATA_DIR, "bm25_index.pkl")
    
    # 3. External API Mocks
    MOCK_API_URL = os.getenv("MOCK_API_URL", "https://jsonplaceholder.typicode.com/posts")
    
    # 4. PayPal Configuration
    PAYPAL_BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_SECRET = os.getenv("PAYPAL_SECRET", "")
