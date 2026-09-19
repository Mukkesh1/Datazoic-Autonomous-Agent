import chromadb
import pickle
import os
from rank_bm25 import BM25Okapi
from typing import List
from app.tools.schemas import ToolMetadata
from app.core.config import Config

class HybridRetriever:
    """
    Combines Vector Search (ChromaDB) and Keyword Search (BM25).
    """
    def __init__(self, embedding_function):
        self.chroma_path = Config.CHROMA_DB_DIR
        self.bm25_path = Config.BM25_INDEX_FILE
        self.embedding_function = embedding_function
        
        os.makedirs(os.path.dirname(self.bm25_path), exist_ok=True)
        
        # Use PersistentClient for on-disk storage
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="tool_collection", 
            embedding_function=self.embedding_function
        )
        
        self.bm25: BM25Okapi = None
        self.tool_ids: List[str] = []

    def needs_indexing(self, tools: List[ToolMetadata]) -> bool:
        """Determines if we need to run the heavy embedding process."""
        # 1. Missing BM25 index?
        if not os.path.exists(self.bm25_path):
            return True
            
        # 2. Tool count mismatch?
        if self.collection.count() != len(tools):
            return True
            
        return False

    def load_index(self) -> None:
        """Loads the fast in-memory components (BM25) from disk."""
        with open(self.bm25_path, "rb") as f:
            data = pickle.load(f)
            self.bm25 = data["bm25"]
            self.tool_ids = data["tool_ids"]

    def index_tools(self, tools: List[ToolMetadata]) -> None:
        """Indexes all tools into both ChromaDB and BM25."""
        if not tools:
            return

        # Wipe existing collection for a clean slate
        try:
            self.client.delete_collection("tool_collection")
        except Exception:
            pass
        
        self.collection = self.client.create_collection(
            name="tool_collection", 
            embedding_function=self.embedding_function
        )

        ids = []
        documents = []
        metadatas = []
        
        for tool in tools:
            doc = f"{tool.name} {tool.description} {' '.join(tool.tags)}"
            ids.append(tool.tool_id)
            documents.append(doc)
            metadatas.append({"name": tool.name})
            
        self.tool_ids = ids

        # 1. Index into ChromaDB (Vector Search) in batches to prevent Ollama memory crashes
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size]
            )

        # 2. Index into BM25 (Keyword Search)
        import re
        tokenized_docs = [re.sub(r'[\._]', ' ', doc.lower()).split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized_docs)
        
        # Save BM25 and IDs to disk
        with open(self.bm25_path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "tool_ids": self.tool_ids}, f)

    def search(self, query: str, top_k: int = 5) -> List[str]:
        """Runs the hybrid search and returns the top_k tool_ids."""
        
        # 1. Vector Search (Semantic meaning)
        chroma_results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        chroma_ids = chroma_results['ids'][0] if chroma_results['ids'] else []

        # 2. Keyword Search (BM25)
        import re
        tokenized_query = re.sub(r'[\._]', ' ', query.lower()).split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        # Get indices of the top scoring BM25 matches
        top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:top_k]
        bm25_ids = [self.tool_ids[i] for i in top_bm25_indices]

        # 3. Reciprocal Rank Fusion (RRF) - Mathematically combine the ranks
        rrf_scores = {}
        k_rrf = 60 # Standard constant used in RRF algorithms
        
        for rank, tool_id in enumerate(chroma_ids):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + (1.0 / (k_rrf + rank + 1))
            
        for rank, tool_id in enumerate(bm25_ids):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + (1.0 / (k_rrf + rank + 1))

        # Sort tools by their combined RRF score
        fused_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Return only the tool_ids
        return [tool_id for tool_id, score in fused_results[:top_k]]
