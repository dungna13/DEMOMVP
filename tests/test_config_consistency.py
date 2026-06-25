"""
Tests kiểm tra tính nhất quán của HIERARCHY_LABELS với dữ liệu seed trong database.
Chạy từ thư mục gốc: pytest tests/test_config_consistency.py -v
"""

import pytest
from src.config import HIERARCHY_LABELS, EFFECTIVENESS_LABELS, EFFECTIVENESS_BOOST
from src.database.database import seed_doc_types


# ── HIERARCHY_LABELS bao phủ tất cả type trong DB seed ───────────────────────

def test_all_db_seed_types_covered_by_hierarchy_labels():
    """Mọi type_code trong seed_doc_types phải có trong HIERARCHY_LABELS."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE document_types (type_code TEXT PRIMARY KEY, type_name TEXT, hierarchy_rank INTEGER NOT NULL)"
    )
    seed_doc_types(conn)
    rows = conn.execute("SELECT type_code FROM document_types").fetchall()
    conn.close()

    missing = [r["type_code"] for r in rows if r["type_code"] not in HIERARCHY_LABELS]
    assert not missing, f"Các type_code trong DB không có trong HIERARCHY_LABELS: {missing}"


def test_hierarchy_labels_rank_range():
    """Mọi rank trong HIERARCHY_LABELS phải nằm trong khoảng [1, 15]."""
    for doc_type, (rank, name) in HIERARCHY_LABELS.items():
        assert 1 <= rank <= 15, f"{doc_type}: rank {rank} nằm ngoài [1, 15]"


def test_hierarchy_labels_name_not_empty():
    """Mọi tên trong HIERARCHY_LABELS không được rỗng."""
    for doc_type, (rank, name) in HIERARCHY_LABELS.items():
        assert name.strip(), f"{doc_type}: tên hiển thị rỗng"


def test_hien_phap_highest_rank():
    rank, _ = HIERARCHY_LABELS["hien_phap"]
    all_ranks = [r for r, _ in HIERARCHY_LABELS.values()]
    assert rank == max(all_ranks), "Hiến pháp phải có rank cao nhất"


def test_luat_bo_luat_same_rank():
    rank_luat, _ = HIERARCHY_LABELS["luat"]
    rank_bo_luat, _ = HIERARCHY_LABELS["bo_luat"]
    assert rank_luat == rank_bo_luat, "Luật và Bộ luật phải có rank bằng nhau"


def test_nghi_dinh_above_thong_tu():
    rank_nd, _ = HIERARCHY_LABELS["nghi_dinh"]
    rank_tt, _ = HIERARCHY_LABELS["thong_tu"]
    assert rank_nd > rank_tt, "Nghị định phải có rank cao hơn Thông tư"


def test_tinh_above_huyen_above_xa():
    rank_tinh, _ = HIERARCHY_LABELS["quyet_dinh_ubnd_tinh"]
    rank_huyen, _ = HIERARCHY_LABELS["quyet_dinh_ubnd_huyen"]
    rank_xa, _ = HIERARCHY_LABELS["quyet_dinh_ubnd_xa"]
    assert rank_tinh > rank_huyen > rank_xa


# ── EFFECTIVENESS_LABELS ──────────────────────────────────────────────────────

def test_effectiveness_labels_covers_all_boost_keys():
    """Mọi key trong EFFECTIVENESS_BOOST phải có icon trong EFFECTIVENESS_LABELS."""
    missing = [k for k in EFFECTIVENESS_BOOST if k not in EFFECTIVENESS_LABELS]
    assert not missing, f"Thiếu icon cho: {missing}"


def test_effectiveness_labels_icons_not_empty():
    for status, icon in EFFECTIVENESS_LABELS.items():
        assert icon.strip(), f"{status}: icon rỗng"


def test_effectiveness_labels_unique_icons():
    icons = list(EFFECTIVENESS_LABELS.values())
    assert len(icons) == len(set(icons)), "Các icon effectiveness phải khác nhau"
