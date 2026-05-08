"""
embedding_service.py — Phase 2: Embedding + Qdrant Vector Store
Sinh vector embeddings cho chunks, quản lý Qdrant collection
"""

import logging
from typing import List, Dict, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)

# Lazy-load heavy imports
_model = None
_qdrant_client = None
_collection_ready = False


def _get_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from config import EMBEDDING_MODEL, EMBEDDING_DEVICE
        logger.info(f"[Embedding] Loading model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
        logger.info(f"[Embedding] Model loaded. Dim={_model.get_sentence_embedding_dimension()}")
    return _model


def _get_qdrant():
    """Lazy-load Qdrant client."""
    global _qdrant_client, _collection_ready
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from config import QDRANT_MODE, QDRANT_URL, QDRANT_PATH, QDRANT_COLLECTION, EMBEDDING_DIM

        if QDRANT_MODE == "memory":
            _qdrant_client = QdrantClient(":memory:")
            logger.info("[Qdrant] Started in-memory mode")
        elif QDRANT_MODE == "local":
            _qdrant_client = QdrantClient(path=QDRANT_PATH)
            logger.info(f"[Qdrant] Started local persistent mode at {QDRANT_PATH}")
        else:
            _qdrant_client = QdrantClient(url=QDRANT_URL)
            logger.info(f"[Qdrant] Connected to {QDRANT_URL}")

        # Tạo collection nếu chưa có
        collections = [c.name for c in _qdrant_client.get_collections().collections]
        if QDRANT_COLLECTION not in collections:
            _qdrant_client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"[Qdrant] Created collection '{QDRANT_COLLECTION}'")
        _collection_ready = True

    return _qdrant_client


def encode_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """Sinh embeddings cho danh sách texts."""
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,  # L2 normalize → cosine = dot product
    )
    return embeddings


def encode_query(query: str) -> np.ndarray:
    """Sinh embedding cho 1 query."""
    model = _get_model()
    return model.encode(query, normalize_embeddings=True)


def index_chunks(chunks: List[Dict[str, Any]], doc_ids_to_mark: Optional[List[int]] = None) -> int:
    """
    Đưa chunks vào Qdrant và đánh dấu documents đã index.
    """
    if not chunks:
        return 0

    from qdrant_client.models import PointStruct
    from config import QDRANT_COLLECTION
    from database import get_db

    client = _get_qdrant()

    # Sinh embeddings
    texts = [c["content"] for c in chunks]
    embeddings = encode_texts(texts)

    # Tạo points
    points = []
    for i, chunk in enumerate(chunks):
        payload = {
            "document_id": chunk["document_id"],
            "chunk_index": chunk.get("chunk_index", i),
            "dieu": chunk.get("dieu"),
            "khoan": chunk.get("khoan"),
            "chuong": chunk.get("chuong"),
            "section_id": chunk.get("section_id"),
            "content_preview": chunk["content"][:300],
            "doc_type": chunk.get("doc_type", ""),
            "effectiveness_status": chunk.get("effectiveness_status", "con_hieu_luc"),
        }
        points.append(PointStruct(
            id=chunk["id"],
            vector=embeddings[i].tolist(),
            payload=payload,
        ))

    # Upsert theo batch
    batch_size = 100
    for start in range(0, len(points), batch_size):
        batch = points[start:start + batch_size]
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=batch,
        )

    # Đánh dấu đã index trong SQLite
    if doc_ids_to_mark:
        with get_db() as conn:
            conn.execute(
                f"UPDATE documents SET embedding_indexed = 1 WHERE id IN ({','.join(['?']*len(doc_ids_to_mark))})",
                doc_ids_to_mark
            )

    logger.info(f"[Qdrant] Indexed {len(points)} chunks for {len(doc_ids_to_mark) if doc_ids_to_mark else 'unknown'} documents")
    return len(points)


def vector_search(
    query: str,
    top_k: int = 20,
    doc_type: Optional[str] = None,
    effectiveness_status: Optional[str] = None,
) -> List[Dict]:
    """
    Tìm kiếm ngữ nghĩa trên Qdrant.
    Returns: list of {id, score, payload}
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from config import QDRANT_COLLECTION

    client = _get_qdrant()
    query_vector = encode_query(query)

    # Build filter
    conditions = []
    if doc_type:
        conditions.append(FieldCondition(
            key="doc_type",
            match=MatchValue(value=doc_type),
        ))
    if effectiveness_status:
        conditions.append(FieldCondition(
            key="effectiveness_status",
            match=MatchValue(value=effectiveness_status),
        ))

    search_filter = Filter(must=conditions) if conditions else None

    results = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector.tolist(),
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )

    return [
        {
            "id": hit.id,
            "score": hit.score,
            "payload": hit.payload,
        }
        for hit in results
    ]


def get_collection_info() -> Dict:
    """Trả về thông tin collection (số points, etc.)."""
    from config import QDRANT_COLLECTION
    try:
        client = _get_qdrant()
        info = client.get_collection(QDRANT_COLLECTION)
        return {
            "collection": QDRANT_COLLECTION,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": str(info.status),
        }
    except Exception as e:
        return {"error": str(e)}


def reindex_all_chunks():
    """
    Đọc chunks của các văn bản CHƯA index từ SQLite → Qdrant.
    """
    from database import get_db
    from config import QDRANT_MODE
    
    # Nếu dùng memory mode, Qdrant bị reset mỗi khi restart
    # Nên ta phải re-index TOÀN BỘ nếu count trong Qdrant = 0
    client = _get_qdrant()
    collection_info = client.get_collection("vanban_chunks")
    
    if QDRANT_MODE == "memory" and collection_info.points_count == 0:
        logger.info("[Reindex] Memory mode detected with empty collection. Resetting index flags...")
        with get_db() as conn:
            conn.execute("UPDATE documents SET embedding_indexed = 0")

    logger.info("[Reindex] Checking for unindexed documents...")

    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.document_id, c.section_id, c.content,
                   c.chunk_index, c.dieu, c.khoan, c.chuong,
                   d.doc_type, d.effectiveness_status
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.embedding_indexed = 0
              AND c.content IS NOT NULL AND LENGTH(c.content) > 10
        """).fetchall()

    if not rows:
        logger.info("[Reindex] No new documents to index.")
        return 0

    chunks = [dict(row) for row in rows]
    doc_ids = list(set(c["document_id"] for c in chunks))
    
    logger.info(f"[Reindex] Found {len(chunks)} chunks from {len(doc_ids)} new documents. Indexing...")
    count = index_chunks(chunks, doc_ids_to_mark=doc_ids)
    logger.info(f"[Reindex] Done. Indexed {count} chunks.")
    return count
