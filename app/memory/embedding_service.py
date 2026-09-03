"""Embedding service for Continuous Learning Vectorized Memory (Memory RAG)."""

import os
import math
import hashlib
import logging
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Generates vector embeddings and computes semantic similarities for memory items."""

    def __init__(self, default_api_key: Optional[str] = None):
        self.default_api_key = default_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")

    @staticmethod
    def calculate_cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity between two float vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        
        return dot / (norm1 * norm2)

    def _generate_fallback_embedding(self, text: str, dimensions: int = 768) -> List[float]:
        """Generate a deterministic normalized pseudo-embedding fallback when no API key is available."""
        words = text.lower().strip().split()
        vector = [0.0] * dimensions
        
        for word in words:
            # Hash words across dimensions
            h = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
            idx = h % dimensions
            vector[idx] += 1.0

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector

    def _ensure_768_dim(self, vec: List[float]) -> List[float]:
        """Guarantee that vector is exactly 768 dimensions and unit normalized."""
        if not vec:
            return [0.0] * 768
        if len(vec) > 768:
            vec = vec[:768]
        elif len(vec) < 768:
            vec = vec + [0.0] * (768 - len(vec))
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        return vec

    async def embed_text(self, text: str, api_key: Optional[str] = None) -> List[float]:
        """Generate embedding vector for a single text string."""
        if not text or not text.strip():
            return [0.0] * 768

        key = api_key or self.default_api_key
        
        # 1. Try Gemini Embeddings (Primary)
        if key:
            try:
                from google import genai
                client = genai.Client(api_key=key)
                res = client.models.embed_content(
                    model="text-embedding-004",
                    contents=text.strip(),
                    config={"output_dimensionality": 768}
                )
                if res.embeddings and len(res.embeddings) > 0:
                    return self._ensure_768_dim(res.embeddings[0].values)
            except Exception as gemini_err:
                try:
                    res = client.models.embed_content(
                        model="gemini-embedding-001",
                        contents=text.strip(),
                        config={"output_dimensionality": 768}
                    )
                    if res.embeddings and len(res.embeddings) > 0:
                        return self._ensure_768_dim(res.embeddings[0].values)
                except Exception as g2_err:
                    logger.debug(f"Gemini embed error, trying fallback/OpenAI: {gemini_err} / {g2_err}")

        # 2. Try OpenAI Embeddings (Secondary)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                oai = OpenAI(api_key=openai_key)
                res = oai.embeddings.create(
                    input=text.strip(),
                    model="text-embedding-3-small",
                    dimensions=768
                )
                if res.data and len(res.data) > 0:
                    return self._ensure_768_dim(res.data[0].embedding)
            except Exception as oai_err:
                logger.debug(f"OpenAI embed error: {oai_err}")

        # 3. Deterministic Local Fallback
        return self._generate_fallback_embedding(text)

    async def embed_batch(self, texts: List[str], api_key: Optional[str] = None) -> List[List[float]]:
        """Generate embeddings for a list of text strings in a single batch."""
        if not texts:
            return []

        cleaned_texts = [t.strip() for t in texts if t and t.strip()]
        if not cleaned_texts:
            return [[0.0] * 768] * len(texts)

        key = api_key or self.default_api_key

        # 1. Try Gemini Batch Embeddings
        if key:
            try:
                from google import genai
                client = genai.Client(api_key=key)
                res = client.models.embed_content(
                    model="text-embedding-004",
                    contents=cleaned_texts,
                    config={"output_dimensionality": 768}
                )
                if res.embeddings and len(res.embeddings) == len(cleaned_texts):
                    return [self._ensure_768_dim(emb.values) for emb in res.embeddings]
            except Exception as gemini_err:
                try:
                    res = client.models.embed_content(
                        model="gemini-embedding-001",
                        contents=cleaned_texts,
                        config={"output_dimensionality": 768}
                    )
                    if res.embeddings and len(res.embeddings) == len(cleaned_texts):
                        return [self._ensure_768_dim(emb.values) for emb in res.embeddings]
                except Exception as g2_err:
                    logger.debug(f"Gemini batch embed error: {gemini_err} / {g2_err}")

        # 2. Try OpenAI Batch Embeddings
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                oai = OpenAI(api_key=openai_key)
                res = oai.embeddings.create(
                    input=cleaned_texts,
                    model="text-embedding-3-small",
                    dimensions=768
                )
                if res.data and len(res.data) == len(cleaned_texts):
                    return [self._ensure_768_dim(d.embedding) for d in res.data]
            except Exception as oai_err:
                logger.debug(f"OpenAI batch embed error: {oai_err}")

        # 3. Fallback per text
        return [self._generate_fallback_embedding(t) for t in texts]
