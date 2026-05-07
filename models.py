"""
models.py — Pydantic schemas cho Phase 1 MVP
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ========== DOCUMENT ==========

class DocumentBase(BaseModel):
    doc_number: str
    title: str
    doc_type: str = "quyet_dinh"
    issuing_date: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    effectiveness_status: str = "con_hieu_luc"
    issuing_authority: Optional[str] = None
    signer: Optional[str] = None
    summary: Optional[str] = None
    source_url: Optional[str] = None


class DocumentOut(DocumentBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


# ========== SECTION ==========

class SectionOut(BaseModel):
    id: int
    document_id: int
    parent_id: Optional[int] = None
    section_type: str
    number: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None

    class Config:
        from_attributes = True


# ========== CHUNK ==========

class ChunkOut(BaseModel):
    id: int
    document_id: int
    content: str
    chunk_index: int
    dieu: Optional[int] = None
    khoan: Optional[int] = None
    chuong: Optional[int] = None

    class Config:
        from_attributes = True


# ========== SEARCH ==========

class SearchResult(BaseModel):
    document: DocumentOut
    highlight: str
    score: float
    matched_sections: List[str] = []


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]
    facets: dict = {}


# ========== DOCUMENT DETAIL ==========

class DocumentDetail(DocumentOut):
    content_markdown: Optional[str] = None
    chunks: List[ChunkOut] = []
    sections: List[SectionOut] = []


# ========== LOẠI VĂN BẢN ==========

DOC_TYPE_LABELS = {
    "luat": "Luật",
    "phap_lenh": "Pháp lệnh",
    "nghi_dinh": "Nghị định",
    "thong_tu": "Thông tư",
    "quyet_dinh": "Quyết định",
    "nghi_quyet": "Nghị quyết",
    "cong_van": "Công văn",
    "chi_thi": "Chỉ thị",
    "an_le": "Án lệ",
}

EFFECTIVENESS_LABELS = {
    "con_hieu_luc": "Còn hiệu lực",
    "het_hieu_luc": "Hết hiệu lực",
    "chua_co_hieu_luc": "Chưa có hiệu lực",
    "het_hieu_luc_mot_phan": "Hết hiệu lực một phần",
}

EFFECTIVENESS_COLORS = {
    "con_hieu_luc": "status-active",
    "het_hieu_luc": "status-expired",
    "chua_co_hieu_luc": "status-pending",
    "het_hieu_luc_mot_phan": "status-partial",
}
