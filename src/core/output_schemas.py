"""
Pydantic schemas cho LangChain structured output.
Thay thế manual json.loads() + regex parsing trong ai_service.py.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CitationItem(BaseModel):
    doc_number: str = Field(description="Số hiệu văn bản, ví dụ: 91/2015/QH13")
    doc_title: str = Field(description="Tên văn bản pháp luật")
    dieu: Optional[int] = Field(None, description="Số điều được trích dẫn")
    khoan: Optional[int] = Field(None, description="Số khoản được trích dẫn")
    content_preview: str = Field(description="Trích dẫn ngắn từ văn bản, tối đa 300 ký tự")


class QAResponse(BaseModel):
    """Output schema cho generate_qa_answer()."""
    answer: str = Field(description="Câu trả lời tổng hợp bằng tiếng Việt, chỉ dựa trên context")
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="Danh sách các điều/khoản văn bản pháp luật được trích dẫn"
    )


class AutoTagResult(BaseModel):
    """Output schema cho auto_tag()."""
    fields: List[str] = Field(
        default_factory=list,
        description="Danh sách lĩnh vực pháp lý phù hợp"
    )
    confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy phân loại từ 0.0 đến 1.0"
    )
