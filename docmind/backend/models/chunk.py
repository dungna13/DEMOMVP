from typing import Optional, Any, Dict
from pydantic import BaseModel

class Chunk(BaseModel):
    id: str
    source_id: str
    index: int
    text: str
    token_count: int
    page: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    # Vietnamese legal document metadata
    dieu: Optional[Any] = None       # Điều (Article)
    khoan: Optional[Any] = None      # Khoản (Clause)
    chuong: Optional[str] = None     # Chương (Chapter)
    # Document identification metadata
    document_number: Optional[str] = None   # Số ký hiệu (e.g., 689/QĐ-TTg)
    issuance_date: Optional[str] = None     # Ngày ban hành (e.g., 15/04/2026)
    issuing_authority: Optional[str] = None # Cơ quan ban hành
