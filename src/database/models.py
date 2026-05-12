"""
models.py — Pydantic schemas cho Phase 1 + Phase 2
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


# ========== PHASE 2: RELATIONS ==========

class RelationOut(BaseModel):
    id: int
    source_doc_id: int
    target_doc_id: Optional[int] = None
    target_doc_number: Optional[str] = None
    relation_type: str
    source_section: Optional[str] = None
    target_section: Optional[str] = None
    detected_by: str = "regex"
    confidence: float = 1.0
    target_title: Optional[str] = None
    target_doc_type: Optional[str] = None
    target_effectiveness: Optional[str] = None

    class Config:
        from_attributes = True


# ========== PHASE 2: LEGAL FIELDS ==========

class LegalFieldOut(BaseModel):
    id: int
    document_id: int
    field_name: str
    confidence: float = 1.0
    source: str = "auto"

    class Config:
        from_attributes = True


# ========== PHASE 2: Q&A ==========

class QARequest(BaseModel):
    question: str
    chat_history: Optional[List[dict]] = None


class QACitation(BaseModel):
    index: int
    doc_id: Optional[int] = None
    doc_number: str = ""
    doc_title: str = ""
    dieu: Optional[int] = None
    khoan: Optional[int] = None
    content_preview: str = ""


class QAResponse(BaseModel):
    question: str
    answer: str
    citations: List[QACitation] = []
    model: str = ""
    chunks_used: int = 0
    ai_available: bool = False


# ========== PHASE 2: HYBRID SEARCH ==========

class HybridSearchResult(BaseModel):
    document: DocumentOut
    highlight: str
    score: float
    search_sources: List[str] = []
    search_mode: str = "balanced"


class HybridSearchResponse(BaseModel):
    query: str
    total: int
    results: List[HybridSearchResult]
    facets: dict = {}
    search_mode: str = "balanced"
    vector_available: bool = False


# ========== RELATION LABELS ==========

RELATION_TYPE_LABELS = {
    "thay_the": "Thay thế",
    "sua_doi": "Sửa đổi, bổ sung",
    "huong_dan": "Hướng dẫn thi hành",
    "bai_bo": "Bãi bỏ",
    "vien_dan": "Viện dẫn",
    "dinh_chinh": "Đính chính",
}

RELATION_TYPE_ICONS = {
    "thay_the": "🔄",
    "sua_doi": "✏️",
    "huong_dan": "📖",
    "bai_bo": "❌",
    "vien_dan": "🔗",
    "dinh_chinh": "📝",
}
# ========== PHASE 3: WIKI DATA ==========

class WikiQAPair(BaseModel):
    question: str
    answer: str


class WikiData(BaseModel):
    summary: str
    key_points: List[str] = []
    legal_fields: List[str] = []
    suggested_questions: List[WikiQAPair] = []
    entities: dict = {}


class WikiDocument(BaseModel):
    source_id: str
    document_number: str
    title: str
    wiki_data: WikiData
    model: str = ""
    processed_at: str = ""
