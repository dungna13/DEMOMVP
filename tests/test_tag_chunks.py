"""
Tests cho tag_chunks() và tag_node() trong rag_engine.py.
Chạy từ thư mục gốc: pytest tests/test_tag_chunks.py -v
"""

from src.core.rag_engine import tag_chunks, tag_node
from src.config import HIERARCHY_LABELS, EFFECTIVENESS_LABELS


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(doc_type: str = "", effectiveness_status: str = "con_hieu_luc", **kwargs) -> dict:
    return {
        "doc_type": doc_type,
        "effectiveness_status": effectiveness_status,
        "content": "nội dung test",
        "document_id": 1,
        **kwargs,
    }


# ── tag_chunks: input/output cơ bản ──────────────────────────────────────────

def test_empty_input_returns_empty():
    assert tag_chunks([]) == []


def test_returns_same_count():
    chunks = [make_chunk("luat"), make_chunk("nghi_dinh")]
    assert len(tag_chunks(chunks)) == len(chunks)


def test_tag_key_added_to_each_chunk():
    result = tag_chunks([make_chunk("luat")])
    assert "_tag" in result[0]


def test_original_chunk_not_mutated():
    original = make_chunk("luat", "con_hieu_luc")
    tag_chunks([original])
    assert "_tag" not in original


# ── tag_chunks: doc_type mapping ─────────────────────────────────────────────

def test_luat_rank_14():
    result = tag_chunks([make_chunk("luat")])
    assert "14/15" in result[0]["_tag"]
    assert "LUẬT" in result[0]["_tag"]


def test_hien_phap_rank_15():
    result = tag_chunks([make_chunk("hien_phap")])
    assert "15/15" in result[0]["_tag"]


def test_nghi_dinh_rank_11():
    result = tag_chunks([make_chunk("nghi_dinh")])
    assert "11/15" in result[0]["_tag"]


def test_thong_tu_rank_8():
    result = tag_chunks([make_chunk("thong_tu")])
    assert "8/15" in result[0]["_tag"]


def test_all_hierarchy_labels_produce_correct_rank_and_name():
    for doc_type, (expected_rank, expected_name) in HIERARCHY_LABELS.items():
        result = tag_chunks([make_chunk(doc_type)])
        tag = result[0]["_tag"]
        assert f"{expected_rank}/15" in tag, f"{doc_type}: expected rank {expected_rank}/15 in '{tag}'"
        assert expected_name in tag, f"{doc_type}: expected name '{expected_name}' in '{tag}'"


def test_unknown_doc_type_fallback_shows_van_ban():
    result = tag_chunks([make_chunk("")])
    assert "VĂN BẢN" in result[0]["_tag"]


def test_unknown_doc_type_nonstandard_string():
    result = tag_chunks([make_chunk("bao_cao_tong_hop")])
    tag = result[0]["_tag"]
    # Fallback rank 9 cho unknown type (xem tag_chunks: default=(9, ...))
    assert "9/15" in tag
    assert "BAO_CAO_TONG_HOP" in tag


# ── tag_chunks: effectiveness mapping ────────────────────────────────────────

def test_con_hieu_luc_shows_green():
    result = tag_chunks([make_chunk("luat", "con_hieu_luc")])
    assert "🟢" in result[0]["_tag"]


def test_het_hieu_luc_shows_red():
    result = tag_chunks([make_chunk("luat", "het_hieu_luc")])
    assert "🔴" in result[0]["_tag"]


def test_chua_co_hieu_luc_shows_blue():
    result = tag_chunks([make_chunk("luat", "chua_co_hieu_luc")])
    assert "🔵" in result[0]["_tag"]


def test_het_hieu_luc_mot_phan_shows_yellow():
    result = tag_chunks([make_chunk("luat", "het_hieu_luc_mot_phan")])
    assert "🟡" in result[0]["_tag"]


def test_unknown_effectiveness_shows_white_circle():
    result = tag_chunks([make_chunk("luat", "trang_thai_la")])
    assert "⚪" in result[0]["_tag"]


def test_all_effectiveness_labels_produce_correct_icon():
    for status, expected_icon in EFFECTIVENESS_LABELS.items():
        result = tag_chunks([make_chunk("luat", status)])
        assert expected_icon in result[0]["_tag"], f"{status}: expected '{expected_icon}'"


# ── tag_chunks: tag format tổng thể ──────────────────────────────────────────

def test_tag_format_contains_slash_15():
    result = tag_chunks([make_chunk("nghi_dinh", "con_hieu_luc")])
    assert "/15" in result[0]["_tag"]


def test_tag_format_brackets():
    result = tag_chunks([make_chunk("luat", "con_hieu_luc")])
    tag = result[0]["_tag"]
    assert tag.startswith("[") and tag.endswith("]")


def test_tag_complete_format_luat_active():
    result = tag_chunks([make_chunk("luat", "con_hieu_luc")])
    assert result[0]["_tag"] == "[🟢 | LUẬT | Hiệu lực pháp lý: 14/15]"


def test_tag_complete_format_nghi_dinh_expired():
    result = tag_chunks([make_chunk("nghi_dinh", "het_hieu_luc")])
    assert result[0]["_tag"] == "[🔴 | NGHỊ ĐỊNH | Hiệu lực pháp lý: 11/15]"


# ── tag_chunks: các trường khác không bị ảnh hưởng ──────────────────────────

def test_other_fields_preserved():
    chunk = make_chunk("luat", "con_hieu_luc", doc_number="45/2019/QH14", dieu="5", khoan="1")
    result = tag_chunks([chunk])
    assert result[0]["doc_number"] == "45/2019/QH14"
    assert result[0]["dieu"] == "5"
    assert result[0]["khoan"] == "1"
    assert result[0]["content"] == "nội dung test"


# ── tag_node ──────────────────────────────────────────────────────────────────

def test_tag_node_sets_tagged_chunks():
    state = {"expanded_chunks": [make_chunk("luat", "con_hieu_luc")]}
    result = tag_node(state)
    assert "tagged_chunks" in result
    assert len(result["tagged_chunks"]) == 1
    assert "_tag" in result["tagged_chunks"][0]


def test_tag_node_empty_expanded_chunks():
    state = {"expanded_chunks": []}
    result = tag_node(state)
    assert result["tagged_chunks"] == []


def test_tag_node_missing_expanded_chunks_key():
    state = {}
    result = tag_node(state)
    assert result["tagged_chunks"] == []


def test_tag_node_does_not_modify_expanded_chunks():
    original_chunk = make_chunk("luat")
    state = {"expanded_chunks": [original_chunk]}
    tag_node(state)
    assert "_tag" not in state["expanded_chunks"][0]
