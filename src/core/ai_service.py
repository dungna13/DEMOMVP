"""
ai_service.py — Phase 2: LLM Abstraction Layer
Auto-summarization, auto-tagging, Q&A generation
Sử dụng litellm để hỗ trợ nhiều LLM provider
"""

import json
import logging
from typing import List, Dict, Optional, Any

from src.config import (
    LLM_MODEL, LLM_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,
    LEGAL_FIELDS, AUTO_TAG_CONFIDENCE_THRESHOLD,
    RAG_TEMPERATURE,
)
from prompts.system_prompt import (
    RAG_QA_PROMPT,
    SUMMARIZE_LVL1_PROMPT,
    SUMMARIZE_LVL2_PROMPT,
    AUTO_TAG_PROMPT,
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
        if GEMINI_API_KEY:
            import os
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

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
            {"role": "system", "content": SUMMARIZE_LVL1_PROMPT},
            {"role": "user", "content": f"Văn bản {doc_number}:\n\n{truncated}"},
        ]
    else:
        # Level 2: Tóm tắt chi tiết
        messages = [
            {"role": "system", "content": SUMMARIZE_LVL2_PROMPT},
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
        {"role": "system", "content": AUTO_TAG_PROMPT.format(fields_str=fields_str)},
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
    RAG Q&A: Sinh câu trả lời pháp luật dựa trên context chunks (Strict RAG với JSON Mode).
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
        doc_info = f"Tài liệu [{i+1}] (Số hiệu: {chunk.get('doc_number', 'N/A')}, Tên: {chunk.get('doc_title', 'N/A')}"
        if chunk.get("dieu"):
            doc_info += f", Điều {chunk['dieu']}"
        if chunk.get("khoan"):
            doc_info += f", Khoản {chunk['khoan']}"
        doc_info += ")"
        context_parts.append(f"{doc_info}:\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    system_prompt = RAG_QA_PROMPT

    if summary:
        system_prompt += f"\n\nBối cảnh hội thoại hiện tại (Ký ức dài hạn / Thông tin đã trao đổi trước đây): {summary}"

    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history if available
    if chat_history:
        for msg in chat_history:
            messages.append(msg)

    messages.append({
        "role": "user",
        "content": f"Context:\n\n{context}\n\n---\n\nCâu hỏi: {question}",
    })

    response_content = ""
    try:
        import litellm
        # Set API keys
        if LLM_API_KEY:
            import os
            os.environ["OPENAI_API_KEY"] = LLM_API_KEY
        if ANTHROPIC_API_KEY:
            import os
            os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        if GEMINI_API_KEY:
            import os
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

        # Thử gọi JSON Mode nếu cấu hình phù hợp
        response = litellm.completion(
            model=LLM_MODEL,
            messages=messages,
            temperature=RAG_TEMPERATURE,
            max_tokens=2000,
            response_format={ "type": "json_object" } if ("gemini" in LLM_MODEL or "gpt" in LLM_MODEL) else None
        )
        response_content = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[AI] RAG completion call failed: {e}")
        # Fallback to general LLM call
        response_content = _call_llm(messages, temperature=RAG_TEMPERATURE, max_tokens=2000)

    # Parse JSON kết quả
    answer = ""
    citations = []
    if response_content:
        try:
            # Dọn sạch block markdown ```json nếu LLM tự chèn thêm
            clean_content = response_content
            if clean_content.startswith("```"):
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                else:
                    clean_content = clean_content[3:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]
                clean_content = clean_content.strip()

            parsed = json.loads(clean_content)
            answer = parsed.get("answer", "")
            citations = parsed.get("citations", [])
            # Map index number to match frontend expectations
            for idx, cit in enumerate(citations, 1):
                cit["index"] = idx
                # Map field names if they mismatch template requirements
                if "doc_id" not in cit:
                    cit["doc_id"] = None
                if "doc_number" not in cit and "document_number" in cit:
                    cit["doc_number"] = cit["document_number"]
                if "doc_title" not in cit and "document_name" in cit:
                    cit["doc_title"] = cit["document_name"]
                if "dieu" not in cit and "article" in cit:
                    # extract number from article text
                    import re
                    m = re.search(r'\d+', cit["article"])
                    cit["dieu"] = int(m.group(0)) if m else None
                if "khoan" not in cit and "clause" in cit:
                    import re
                    m = re.search(r'\d+', cit["clause"])
                    cit["khoan"] = int(m.group(0)) if m else None
        except Exception as e:
            logger.warning(f"[AI] Failed to parse JSON response: {e}. Raw: {response_content}")
            answer = response_content
            # Fallback citations from context_chunks
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
        return bool(LLM_API_KEY or ANTHROPIC_API_KEY or GEMINI_API_KEY)
    except ImportError:
        return False
