"""
Tests cho rerank_chunks() — đảm bảo type_boost từ HIERARCHY_LABELS hoạt động đúng.
Chạy từ thư mục gốc: pytest tests/test_rerank_chunks.py -v
"""

import pytest
from src.core.rag_engine import rerank_chunks


def make_chunk(doc_type: str, effectiveness_status: str = "con_hieu_luc", score: float = 1.0, **kwargs) -> dict:
    return {
        "doc_type": doc_type,
        "effectiveness_status": effectiveness_status,
        "score": score,
        "content": "test",
        "document_id": 1,
        **kwargs,
    }


# ── Kết quả cơ bản ───────────────────────────────────────────────────────────

def test_empty_input_returns_empty():
    assert rerank_chunks([]) == []


def test_returns_at_most_top_k():
    chunks = [make_chunk("luat") for _ in range(20)]
    result = rerank_chunks(chunks, top_k=5)
    assert len(result) <= 5


def test_rerank_score_added():
    chunks = [make_chunk("luat")]
    result = rerank_chunks(chunks)
    assert "rerank_score" in result[0]


# ── Sắp xếp theo thứ bậc pháp lý ────────────────────────────────────────────

def test_luat_ranked_above_thong_tu_same_base_score():
    luat_chunk = make_chunk("luat", score=1.0)
    thong_tu_chunk = make_chunk("thong_tu", score=1.0)
    result = rerank_chunks([thong_tu_chunk, luat_chunk])
    assert result[0]["doc_type"] == "luat"


def test_hien_phap_ranked_above_nghi_dinh():
    hp = make_chunk("hien_phap", score=1.0)
    nd = make_chunk("nghi_dinh", score=1.0)
    result = rerank_chunks([nd, hp])
    assert result[0]["doc_type"] == "hien_phap"


def test_higher_base_score_can_override_lower_rank():
    # Thông tư score=10 vs Luật score=0.1 → Thông tư vẫn win vì base score cao hơn nhiều
    thong_tu = make_chunk("thong_tu", score=10.0)
    luat = make_chunk("luat", score=0.1)
    result = rerank_chunks([luat, thong_tu])
    assert result[0]["doc_type"] == "thong_tu"


# ── Effectiveness boost ───────────────────────────────────────────────────────

def test_active_doc_ranked_above_expired_same_type():
    active = make_chunk("luat", effectiveness_status="con_hieu_luc", score=1.0)
    expired = make_chunk("luat", effectiveness_status="het_hieu_luc", score=1.0)
    result = rerank_chunks([expired, active])
    assert result[0]["effectiveness_status"] == "con_hieu_luc"


# ── Specificity boost ─────────────────────────────────────────────────────────

def test_chunk_with_dieu_ranked_above_without():
    with_dieu = make_chunk("luat", score=1.0, dieu="5")
    without_dieu = make_chunk("luat", score=1.0)
    result = rerank_chunks([without_dieu, with_dieu])
    assert result[0].get("dieu") == "5"


def test_chunk_with_dieu_and_khoan_ranked_highest():
    full = make_chunk("luat", score=1.0, dieu="5", khoan="2")
    only_dieu = make_chunk("luat", score=1.0, dieu="5")
    no_struct = make_chunk("luat", score=1.0)
    result = rerank_chunks([no_struct, only_dieu, full])
    assert result[0].get("khoan") == "2"


# ── type_boost consistency với HIERARCHY_LABELS ───────────────────────────────

def test_type_boost_monotonic_with_rank():
    """Rank cao hơn phải cho rerank_score cao hơn khi base score và eff bằng nhau."""
    from src.config import HIERARCHY_LABELS
    # lấy 3 loại có rank khác nhau rõ ràng
    types_by_rank = sorted(HIERARCHY_LABELS.items(), key=lambda x: x[1][0])
    low_type = types_by_rank[0][0]    # rank thấp nhất
    mid_type = types_by_rank[len(types_by_rank)//2][0]
    high_type = types_by_rank[-1][0]  # rank cao nhất

    chunks = [
        make_chunk(low_type, score=1.0),
        make_chunk(mid_type, score=1.0),
        make_chunk(high_type, score=1.0),
    ]
    result = rerank_chunks(chunks, top_k=3)
    scores = [c["rerank_score"] for c in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0]["doc_type"] == high_type


def test_unknown_doc_type_uses_rank_5_fallback():
    unknown = make_chunk("loai_khong_ton_tai", score=1.0)
    luat = make_chunk("luat", score=1.0)
    result = rerank_chunks([unknown, luat])
    # Luật rank 14, unknown fallback rank 5 → Luật phải đứng trên
    assert result[0]["doc_type"] == "luat"
