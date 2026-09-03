import pytest
from app.memory.embedding_service import EmbeddingService

def test_cosine_similarity():
    service = EmbeddingService()
    
    # Identical vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert pytest.approx(service.calculate_cosine_similarity(v1, v2), 0.001) == 1.0

    # Orthogonal vectors
    v3 = [0.0, 1.0, 0.0]
    assert pytest.approx(service.calculate_cosine_similarity(v1, v3), 0.001) == 0.0

    # Opposite vectors
    v4 = [-1.0, 0.0, 0.0]
    assert pytest.approx(service.calculate_cosine_similarity(v1, v4), 0.001) == -1.0

    # Empty or mismatched vectors
    assert service.calculate_cosine_similarity([], []) == 0.0
    assert service.calculate_cosine_similarity([1.0], [1.0, 2.0]) == 0.0

@pytest.mark.asyncio
async def test_fallback_embedding():
    service = EmbeddingService()
    emb1 = await service.embed_text("severely allergic to Latex")
    emb2 = await service.embed_text("severely allergic to Latex")
    emb3 = await service.embed_text("prefers video calls on Tuesday evenings")

    assert len(emb1) == 768
    assert len(emb2) == 768
    assert len(emb3) == 768

    # Identical text produces identical embedding
    sim_identical = service.calculate_cosine_similarity(emb1, emb2)
    assert pytest.approx(sim_identical, 0.001) == 1.0

    # Different text produces lower similarity
    sim_diff = service.calculate_cosine_similarity(emb1, emb3)
    assert sim_diff < 0.9

@pytest.mark.asyncio
async def test_batch_embedding():
    service = EmbeddingService()
    texts = [
        "Allergies: severely allergic to Latex and Sulfa drugs",
        "Preferred Time: Friday afternoons after 2 PM",
        "Preferred Doctor: Dr. Emily Roberts"
    ]
    embeddings = await service.embed_batch(texts)
    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 768
