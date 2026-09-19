import chromadb
import os
import hashlib
from typing import List, Dict, Any
from app.core.config import Config

class RAGEngine:
    """
    Retrieval-Augmented Generation (RAG) Engine.
    Manages embedding and searching local markdown knowledge base files.
    """
    def __init__(self, embedding_function):
        self.embedding_function = embedding_function
        
        self.kb_dir = Config.KB_DIR
        self.chroma_path = Config.CHROMA_DB_DIR
        self.hash_path = os.path.join(self.kb_dir, ".rag_hash")
        
        os.makedirs(self.kb_dir, exist_ok=True)
        
        # Use the same persistent client to avoid DB locking issues
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base_collection", 
            embedding_function=self.embedding_function
        )

    def _compute_kb_hash(self) -> str:
        """Computes a combined hash of all markdown files to detect changes."""
        hasher = hashlib.sha256()
        # Sort files to ensure consistent hashing
        files = sorted([f for f in os.listdir(self.kb_dir) if f.endswith(".md")])
        for filename in files:
            filepath = os.path.join(self.kb_dir, filename)
            with open(filepath, "rb") as f:
                hasher.update(f.read())
        return hasher.hexdigest()

    def needs_indexing(self) -> bool:
        """Checks if the markdown files have changed since the last ingestion."""
        current_hash = self._compute_kb_hash()
        
        if not os.path.exists(self.hash_path):
            return True
            
        with open(self.hash_path, "r") as f:
            saved_hash = f.read().strip()
            
        if current_hash != saved_hash:
            return True
            
        # Fallback check in case the DB was wiped but the hash file remained
        if self.collection.count() == 0 and len([f for f in os.listdir(self.kb_dir) if f.endswith(".md")]) > 0:
            return True
            
        return False

    def ingest_documents(self) -> None:
        """Reads markdown files, chunks them by double newline, and indexes them."""
        # Clean slate
        try:
            self.client.delete_collection("knowledge_base_collection")
        except Exception:
            pass
            
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base_collection", 
            embedding_function=self.embedding_function
        )
        
        documents = []
        metadatas = []
        ids = []
        
        files = sorted([f for f in os.listdir(self.kb_dir) if f.endswith(".md")])
        for filename in files:
            filepath = os.path.join(self.kb_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Simple chunking by paragraph/section (split by double newline)
            chunks = [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
            
            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({"source": filename, "chunk_idx": i})
                ids.append(f"{filename}_{i}")
                
        if documents:
            # Batch add to ChromaDB
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                self.collection.add(
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
                
            # Save the new hash
            with open(self.hash_path, "w") as f:
                f.write(self._compute_kb_hash())

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Performs vector search against the knowledge base."""
        if self.collection.count() == 0:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        # Format results nicely for the LLM
        formatted_results = []
        if results["documents"] and results["documents"][0]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                formatted_results.append({
                    "source": meta["source"],
                    "content": doc
                })
                
        return formatted_results
