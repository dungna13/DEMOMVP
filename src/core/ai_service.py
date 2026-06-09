"""
ai_service.py — Phase 2: LLM Abstraction Layer
Auto-summarization, auto-tagging, Q&A generation
Sử dụng litellm để hỗ trợ nhiều LLM provider
"""

import json
import logging
from typing import List, Dict, Optional, Any

from src.config import (
    LLM_MODEL, LLM_API_KEY, ANTHROPIC_API_KEY,
    LEGAL_FIELDS, AUTO_TAG_CONFIDENCE_THRESHOLD,
    RAG_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def _call_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """
    Gọi LLM qua litellm.
    Fallback: nếu litellm không khả dụng, trả về empty string.
    """
    try:
        import litellm
        # Set API keys
        if LLM_API_KEY:
            import os
            os.environ["OPENAI_API_KEY"] = LLM_API_KEY
        if ANTHROPIC_API_KEY:
            import os
            os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

        response = litellm.completion(
            model=model or LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        logger.warning("[AI] litellm not installed. AI features disabled.")
        return ""
    except Exception as e:
        logger.error(f"[AI] LLM call failed: {e}")
        return ""


def auto_summarize(content: str, doc_number: str = "", level: int = 1) -> str:
    """
    Tóm tắt văn bản pháp luật.
    Level 1: 2-3 câu tóm tắt nhanh (dùng 3000 tokens đầu)
    Level 2: Tóm tắt theo cấu trúc Chương/Điều (toàn bộ)
    """
    if not content or len(content.strip()) < 50:
        return ""

    if level == 1:
        # Level 1: Tóm tắt nhanh
        truncated = content[:6000]  # ~3000 tokens
        messages = [
            {"role": "system", "content": """Bạn là chuyên gia pháp luật Việt Nam. 
Tóm tắt văn bản pháp luật sau trong 2-3 câu ngắn gọn bằng tiếng Việt.
Nêu rõ: (1) Đây là loại văn bản gì, (2) Nội dung chính, (3) Đối tượng áp dụng.
Chỉ trả về phần tóm tắt, không thêm tiêu đề hay giải thích."""},
            {"role": "user", "content": f"Văn bản {doc_number}:\n\n{truncated}"},
        ]
    else:
        # Level 2: Tóm tắt chi tiết
        messages = [
            {"role": "system", "content": """Bạn là chuyên gia pháp luật Việt Nam.
Tóm tắt văn bản pháp luật sau theo cấu trúc:
## Tổng quan
(1-2 câu mô tả chung)

## Nội dung chính
- Chương/Phần 1: ...
- Chương/Phần 2: ...

## Điểm mới/quan trọng
- ...

Trả lời bằng tiếng Việt, markdown format."""},
            {"role": "user", "content": f"Văn bản {doc_number}:\n\n{content[:12000]}"},
        ]

    result = _call_llm(messages, temperature=0.1, max_tokens=1000 if level == 1 else 2000)
    if result:
        logger.info(f"[AI] Summarized {doc_number} (level {level})")
    return result


def auto_tag(content: str, existing_fields: Optional[List[str]] = None) -> Dict:
    """
    Gán nhãn lĩnh vực pháp lý tự động.
    Returns: {fields: [...], confidence: float, auto_applied: bool}
    """
    if not content or len(content.strip()) < 50:
        return {"fields": [], "confidence": 0.0, "auto_applied": False}

    fields_list = existing_fields or LEGAL_FIELDS
    fields_str = ", ".join(fields_list)

    messages = [
        {"role": "system", "content": f"""Bạn là chuyên gia phân loại văn bản pháp luật Việt Nam.
Cho trước danh sách lĩnh vực: [{fields_str}]

Phân tích nội dung văn bản và trả về JSON (chỉ JSON, không giải thích):
{{"fields": ["lĩnh_vực_1", "lĩnh_vực_2"], "confidence": 0.XX}}

Quy tắc:
- Chọn 1-3 lĩnh vực phù hợp nhất
- confidence từ 0.0 đến 1.0
- Chỉ chọn lĩnh vực trong danh sách"""},
        {"role": "user", "content": content[:3000]},
    ]

    result = _call_llm(messages, temperature=0.0, max_tokens=200)
    if not result:
        return {"fields": [], "confidence": 0.0, "auto_applied": False}

    try:
        # Parse JSON từ LLM response
        # Xử lý trường hợp LLM trả về text + JSON
        json_start = result.find("{")
        json_end = result.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(result[json_start:json_end])
            fields = parsed.get("fields", [])
            confidence = float(parsed.get("confidence", 0.0))
            auto_applied = confidence >= AUTO_TAG_CONFIDENCE_THRESHOLD
            return {
                "fields": fields,
                "confidence": confidence,
                "auto_applied": auto_applied,
                "model": LLM_MODEL,
            }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[AI] Failed to parse auto-tag response: {e}")

    return {"fields": [], "confidence": 0.0, "auto_applied": False}


def generate_qa_answer(
    question: str,
    context_chunks: List[Dict[str, Any]],
    chat_history: Optional[List[Dict]] = None,
    summary: Optional[str] = None,
) -> Dict:
    """
    RAG Q&A: Sinh câu trả lời pháp luật dựa trên context chunks.
    Returns: {answer: str, citations: [...], model: str}
    """
    if not context_chunks:
        return {
            "answer": "Xin lỗi, tôi không tìm thấy quy định pháp luật liên quan đến câu hỏi của bạn trong cơ sở dữ liệu.",
            "citations": [],
            "model": LLM_MODEL,
        }

    # Build context string
    context_parts = []
    for i, chunk in enumerate(context_chunks):
        doc_info = ""
        if chunk.get("doc_number"):
            doc_info = f" (Văn bản: {chunk['doc_number']}"
            if chunk.get("dieu"):
                doc_info += f", Điều {chunk['dieu']}"
            if chunk.get("khoan"):
                doc_info += f", Khoản {chunk['khoan']}"
            doc_info += ")"

        context_parts.append(f"[{i+1}]{doc_info}:\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    system_prompt = """Bạn là trợ lý pháp luật Việt Nam chuyên nghiệp. Trả lời câu hỏi dựa HOÀN TOÀN trên các tài liệu pháp lý được cung cấp.

QUY TẮC BẮT BUỘC:
1. Mọi khẳng định PHẢI có trích dẫn [số] tương ứng với tài liệu nguồn.
2. PHẠM VI ÁP DỤNG: Nếu tài liệu tìm thấy chỉ quy định cho một đối tượng hoặc lĩnh vực đặc thù (ví dụ: chỉ dành cho thuyền viên, giáo viên, cán bộ y tế...), bạn PHẢI nêu rõ điều này ngay từ đầu câu trả lời để tránh người dùng hiểu lầm là quy định chung.
3. Nếu KHÔNG tìm thấy căn cứ → nói rõ "Không tìm thấy quy định liên quan trong cơ sở dữ liệu".
4. KHÔNG ĐƯỢC bịa thông tin.
5. Phân biệt rõ quy định còn hiệu lực vs đã hết hiệu lực.
6. Nếu có sửa đổi bổ sung → trích dẫn phiên bản mới nhất, ghi chú phiên bản cũ.
7. Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc.

FORMAT:
- Nêu rõ phạm vi áp dụng (Quy định chung hay đặc thù lĩnh vực).
- Trả lời trực tiếp câu hỏi.
- Trích dẫn nguồn bằng [1], [2], ...
- Cuối cùng liệt kê nguồn tham khảo."""

    if summary:
        system_prompt += f"\n\nBối cảnh hội thoại hiện tại (Ký ức dài hạn / Thông tin đã trao đổi trước đây): {summary}"

    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history if available
    if chat_history:
        for msg in chat_history:  # Sử dụng toàn bộ chat_history được truyền vào (đã được cắt ở RAG Engine)
            messages.append(msg)

    messages.append({
        "role": "user",
        "content": f"Tài liệu tham khảo:\n\n{context}\n\n---\n\nCâu hỏi: {question}",
    })

    answer = _call_llm(messages, temperature=RAG_TEMPERATURE, max_tokens=2000)

    # Build citations
    citations = []
    for i, chunk in enumerate(context_chunks):
        citations.append({
            "index": i + 1,
            "doc_id": chunk.get("document_id"),
            "doc_number": chunk.get("doc_number", ""),
            "doc_title": chunk.get("doc_title", ""),
            "dieu": chunk.get("dieu"),
            "khoan": chunk.get("khoan"),
            "content_preview": chunk["content"][:200],
        })

    if not answer:
        answer = "Xin lỗi, hệ thống AI tạm thời không khả dụng. Vui lòng thử lại sau hoặc cấu hình API key trong config.py."

    return {
        "answer": answer,
        "citations": citations,
        "model": LLM_MODEL,
        "chunks_used": len(context_chunks),
    }


def is_ai_available() -> bool:
    """Kiểm tra xem AI service có khả dụng không."""
    try:
        import litellm
        return bool(LLM_API_KEY or ANTHROPIC_API_KEY)
    except ImportError:
        return False
