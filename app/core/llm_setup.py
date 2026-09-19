from langchain_ollama import ChatOllama
import chromadb.utils.embedding_functions as embedding_functions
from app.core.config import Config

# Use ChromaDB's native Ollama embedding function to avoid all LangChain signature clashes
embedding_function = embedding_functions.OllamaEmbeddingFunction(
    model_name=Config.EMBEDDING_MODEL,
    url="http://127.0.0.1:11434/api/embeddings"
)

# The Main LLM (Used for Extraction, Routing, and Synthesis)
extraction_model = ChatOllama(
    model=Config.STRONG_LLM_MODEL,
    temperature=0,
)
