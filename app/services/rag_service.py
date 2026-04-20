"""
RAG Service - ChromaDB for past ticket retrieval
Learn from Done tickets (Ada's approach)
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings


class RAGService:
    """
    Retrieval-Augmented Generation service.
    Indexes past Done tickets and retrieves similar cases for new tickets.
    """
    
    def __init__(self, persist_dir: str = None):
        if persist_dir is None:
            persist_dir = str(Path(__file__).parent.parent.parent / "data" / "chroma_db")
        
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        
        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.collection = self.client.get_or_create_collection(
            name="past_tickets",
            metadata={"description": "Past resolved NOC tickets for RAG"}
        )
    
    def index_past_tickets(self, tickets_dir: str = None) -> int:
        """Index all fetched Done tickets from data/tickets/"""
        if tickets_dir is None:
            tickets_dir = str(Path(__file__).parent.parent.parent / "data" / "tickets")
        
        tickets_path = Path(tickets_dir)
        if not tickets_path.exists():
            return 0
        
        indexed = 0
        
        for ticket_file in tickets_path.glob("NOC-*.json"):
            try:
                with open(ticket_file) as f:
                    data = json.load(f)
                
                analysis = data.get("analysis", {})
                comments = data.get("comments", {}).get("comments", [])
                
                ticket_key = analysis.get("key", ticket_file.stem)
                summary = analysis.get("summary", "")
                description = analysis.get("description", "")
                status = analysis.get("status", "")
                
                # Combine content for embedding
                resolution_text = " ".join([c.get("body", "") for c in comments])
                content = f"Summary: {summary}\nDescription: {description}\nResolution: {resolution_text}"
                
                # Skip if already indexed
                existing = self.collection.get(ids=[ticket_key])
                if existing and existing.get("ids"):
                    continue
                
                # Add to vector DB
                self.collection.add(
                    ids=[ticket_key],
                    documents=[content],
                    metadatas=[{
                        "ticket_key": ticket_key,
                        "summary": summary[:200],
                        "status": status,
                        "resolution_preview": resolution_text[:500] if resolution_text else "No resolution notes"
                    }]
                )
                
                indexed += 1
                print(f"  📚 Indexed {ticket_key}")
                
            except Exception as e:
                print(f"  ❌ Failed to index {ticket_file.name}: {e}")
        
        return indexed
    
    def find_similar_tickets(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Find similar past tickets for a new issue"""
        
        # Check if collection has any tickets
        count = self.collection.count()
        if count == 0:
            return []
        
        n_results = min(n_results, count)
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            similar = []
            if results.get("ids") and results["ids"][0]:
                for i, ticket_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0
                    document = results["documents"][0][i] if results.get("documents") else ""
                    
                    similar.append({
                        "ticket_key": ticket_id,
                        "summary": metadata.get("summary", ""),
                        "status": metadata.get("status", ""),
                        "resolution_preview": metadata.get("resolution_preview", ""),
                        "similarity_score": 1 - distance,  # Convert distance to similarity
                        "content_preview": document[:300]
                    })
            
            return similar
            
        except Exception as e:
            print(f"RAG query error: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG index stats"""
        return {
            "total_indexed": self.collection.count(),
            "persist_dir": self.persist_dir
        }


# Global instance
_rag_service = None

def get_rag_service() -> RAGService:
    """Get or create the global RAG service"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
