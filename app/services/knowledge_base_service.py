import os
import io
import logging
from typing import List, Dict, Any, Optional
from google import genai
from app.system_database import SystemDatabase

logger = logging.getLogger(__name__)

class KnowledgeBaseService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._genai_client = None
        if self.api_key:
            try:
                self._genai_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize GenAI client for KnowledgeBaseService: {e}")
        self.sys_db = SystemDatabase()

    def _get_client(self):
        if not self._genai_client:
            key = self.api_key or os.getenv("GEMINI_API_KEY")
            if key:
                self._genai_client = genai.Client(api_key=key)
        return self._genai_client

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a 768-dimension vector embedding using Gemini gemini-embedding-001."""
        client = self._get_client()
        if not client:
            raise ValueError("GEMINI_API_KEY is not configured for generating embeddings.")
        
        try:
            from google.genai import types
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=768)
            )
            if response and response.embeddings and len(response.embeddings) > 0:
                return response.embeddings[0].values
            raise ValueError("No embeddings returned from Gemini API.")
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}")
            raise e

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Splits long text into overlapping chunks for high-precision retrieval."""
        clean_text = text.strip()
        if not clean_text:
            return []
        
        if len(clean_text) <= chunk_size:
            return [clean_text]

        chunks = []
        start = 0
        while start < len(clean_text):
            end = start + chunk_size
            chunk = clean_text[start:end]
            chunks.append(chunk)
            start += (chunk_size - overlap)
        return chunks

    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        """Extracts plain text from PDF file bytes."""
        text = ""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except ImportError:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            except Exception as e:
                logger.error(f"Failed PDF extraction fallback: {e}")
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            
        return text.strip()

    async def add_entry(
        self, 
        client_id: int, 
        title: str, 
        content: str, 
        file_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunks content, generates vector embeddings, and stores them in client_knowledge_base.
        """
        chunks = self.chunk_text(content)
        if not chunks:
            return []

        pool = await self.sys_db._get_conn()
        saved_records = []

        async with pool.acquire() as conn:
            for i, chunk in enumerate(chunks):
                chunk_title = title if len(chunks) == 1 else f"{title} (Part {i+1})"
                embedding = self.generate_embedding(chunk)
                vector_str = f"[{','.join(map(str, embedding))}]"

                row = await conn.fetchrow("""
                    INSERT INTO client_knowledge_base (client_id, title, content, content_embedding, file_name)
                    VALUES ($1, $2, $3, $4::vector, $5)
                    RETURNING id, client_id, title, content, file_name, created_at;
                """, client_id, chunk_title, chunk, vector_str, file_name)

                saved_records.append(dict(row))

        logger.info(f"Added {len(saved_records)} knowledge base chunks for client {client_id} (title={title!r})")
        return saved_records

    async def list_entries(self, client_id: int) -> List[Dict[str, Any]]:
        """Retrieves all stored knowledge base items for a client."""
        pool = await self.sys_db._get_conn()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, client_id, title, content, file_name, created_at
                FROM client_knowledge_base
                WHERE client_id = $1
                ORDER BY created_at DESC;
            """, client_id)
            return [dict(r) for r in rows]

    async def delete_entry(self, client_id: int, kb_id: int) -> bool:
        """Deletes a knowledge base item by ID and client_id."""
        pool = await self.sys_db._get_conn()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM client_knowledge_base
                WHERE id = $1 AND client_id = $2;
            """, kb_id, client_id)
            deleted_count = int(result.split(" ")[1]) if " " in result else 0
            return deleted_count > 0

    async def search(self, client_id: int, query: str, top_k: int = 3) -> str:
        """
        Executes a Cosine Distance vector search against PostgreSQL pgvector.
        Returns a formatted context string of matching chunks.
        """
        if not query or not query.strip():
            return "No search query provided."

        try:
            query_embedding = self.generate_embedding(query)
            vector_str = f"[{','.join(map(str, query_embedding))}]"

            pool = await self.sys_db._get_conn()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT title, content, file_name, content_embedding <=> $2::vector AS distance
                    FROM client_knowledge_base
                    WHERE client_id = $1
                    ORDER BY distance ASC
                    LIMIT $3;
                """, client_id, vector_str, top_k)

                if not rows:
                    return f"No relevant information found in the knowledge base for query: '{query}'."

                results = []
                for r in rows:
                    source_str = f" (File: {r['file_name']})" if r.get('file_name') else ""
                    results.append(f"--- {r['title']}{source_str} ---\n{r['content']}")

                context_output = "\n\n".join(results)
                logger.info(f"KB Search for client {client_id} (query='{query}') returned {len(rows)} matching chunks.")
                return context_output
        except Exception as e:
            logger.error(f"Error performing KB vector search for client {client_id}: {e}")
            return f"Knowledge Base search error: {str(e)}"
