"""
ai_service.py — LangChain-based LLM Abstraction Layer
Auto-summarization, auto-tagging, Q&A generation
Sử dụng LangChain để hỗ trợ nhiều LLM provider với structured output.
"""

import logging
from typing import List, Dict, Optional, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.language_models import BaseChatModel

from src.config import (
    LLM_MODEL, LLM_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,
    LEGAL_FIELDS, AUTO_TAG_CONFIDENCE_THRESHOLD, RAG_TEMPERATURE,
)
from src.core.output_schemas import QAResponse, AutoTagResult, CitationItem
from prompts.system_prompt import (
    RAG_QA_PROMPT,
    SUMMARIZE_LVL1_PROMPT,
    SUMMARIZE_LVL2_PROMPT,
    AUTO_TAG_PROMPT,
)

logger = logging.getLogger(__name__)

_chat_model: Optional[BaseChatModel] = None


def _get_chat_model(temperature: float = 0.1, max_tokens: int = 2000) -> Optional[BaseChatModel]:
    """
    Factory: trả về LangChain ChatModel phù hợp dựa trên API key có sẵn.
    Ưu tiên: Gemini → OpenAI → Anthropic → Ollama.
    """
    try:
        if GEMINI_API_KEY:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = LLM_MODEL.replace("gemini/", "") if "gemini/" in LLM_MODEL else "gemini-1.5-flash"
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=GEMINI_API_KEY,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        if LLM_API_KEY:
            from langchain_openai import ChatOpenAI
            model_name = LLM_MODEL if not LLM_MODEL.startswith("gpt") else LLM_MODEL
            return ChatOpenAI(
                model=model_name,
                api_key=LLM_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if ANTHROPIC_API_KEY:
            from langchain_anthropic import ChatAnthropic
            model_name = LLM_MODEL if "claude" in LLM_MODEL else "claude-3-haiku-20240307"
            return ChatAnthropic(
                model=model_name,
                api_key=ANTHROPIC_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        # Fallback: Ollama local
        from langchain_ollama import ChatOllama
        ollama_model = LLM_MODEL.replace("ollama/", "") if "ollama/" in LLM_MODEL else "vistral"
        return ChatOllama(model=ollama_model, temperature=temperature)
    except ImportError as e:
        logger.warning(f"[AI] LangChain provider import failed: {e}")
        return None
    except Exception as e:
        logger.error(f"[AI] Failed to initialize chat model: {e}")
        return None


def _call_llm(messages: List[Dict[str, str]], temperature: float = 0.1, max_tokens: int = 1000) -> str:
    """Gọi LLM với danh sách messages thô (role và content) dùng LangChain model."""
    model = _get_chat_model(temperature=temperature, max_tokens=max_tokens)
    if not model:
        return ""
    
    langchain_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            langchain_messages.append(("system", content))
        elif role == "assistant":
            langchain_messages.append(("ai", content))
        else:
            langchain_messages.append(("human", content))
            
    try:
        response = model.invoke(langchain_messages)
        if hasattr(response, "content"):
            return response.content
        return str(response)
    except Exception as e:
        logger.error(f"[AI] _call_llm failed: {e}")
        return ""


def is_ai_available() -> bool:
    """Kiểm tra xem AI service có khả dụng không."""
    return bool(LLM_API_KEY or ANTHROPIC_API_KEY or GEMINI_API_KEY)


def auto_summarize(content: str, doc_number: str = "", level: int = 1) -> str:
    """
    Tóm tắt văn bản pháp luật.
    Level 1: 2-3 câu tóm tắt nhanh
    Level 2: Tóm tắt theo cấu trúc Chương/Điều
    """
    if not content or len(content.strip()) < 50:
        return ""

    model = _get_chat_model(temperature=0.1, max_tokens=1000 if level == 1 else 2000)
    if not model:
        return ""

    system_prompt = SUMMARIZE_LVL1_PROMPT if level == 1 else SUMMARIZE_LVL2_PROMPT
    truncated = content[:6000] if level == 1 else content[:12000]

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Văn bản {doc_number}:\n\n{content}"),
    ])
    chain = prompt | model | StrOutputParser()

    try:
        result = chain.invoke({"doc_number": doc_number, "content": truncated})
        if result:
            logger.info(f"[AI] Summarized {doc_number} (level {level})")
        return result
    except Exception as e:
        logger.error(f"[AI] auto_summarize failed: {e}")
        return ""


def auto_tag(content: str, existing_fields: Optional[List[str]] = None) -> Dict:
    """
    Gán nhãn lĩnh vực pháp lý tự động.
    Returns: {fields: [...], confidence: float, auto_applied: bool}
    """
    if not content or len(content.strip()) < 50:
        return {"fields": [], "confidence": 0.0, "auto_applied": False}

    model = _get_chat_model(temperature=0.0, max_tokens=200)
    if not model:
        return {"fields": [], "confidence": 0.0, "auto_applied": False}

    fields_str = ", ".join(existing_fields or LEGAL_FIELDS)
    parser = PydanticOutputParser(pydantic_object=AutoTagResult)

    prompt = ChatPromptTemplate.from_messages([
        ("system", AUTO_TAG_PROMPT.format(fields_str=fields_str) + "\n\n{format_instructions}"),
        ("human", "{content}"),
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | model | parser

    try:
        result: AutoTagResult = chain.invoke({"content": content[:3000]})
        auto_applied = result.confidence >= AUTO_TAG_CONFIDENCE_THRESHOLD
        return {
            "fields": result.fields,
            "confidence": result.confidence,
            "auto_applied": auto_applied,
            "model": LLM_MODEL,
        }
    except Exception as e:
        logger.warning(f"[AI] auto_tag failed: {e}")
        return {"fields": [], "confidence": 0.0, "auto_applied": False}


def generate_qa_answer(
    question: str,
    context_chunks: List[Dict[str, Any]],
    chat_history: Optional[List[Dict]] = None,
    summary: Optional[str] = None,
) -> Dict:
    """
    RAG Q&A: Sinh câu trả lời pháp luật dựa trên context chunks.
    Dùng PydanticOutputParser thay cho manual JSON parsing.
    Returns: {answer: str, citations: [...], model: str, chunks_used: int}
    """
    if not context_chunks:
        return {
            "answer": "Xin lỗi, tôi không tìm thấy quy định pháp luật liên quan đến câu hỏi của bạn trong cơ sở dữ liệu.",
            "citations": [],
            "model": LLM_MODEL,
            "chunks_used": 0,
        }

    model = _get_chat_model(temperature=RAG_TEMPERATURE, max_tokens=2000)
    if not model:
        return {
            "answer": "Xin lỗi, hệ thống AI tạm thời không khả dụng.",
            "citations": [],
            "model": "none",
            "chunks_used": 0,
        }

    # Build context string
    context_parts = []
    for i, chunk in enumerate(context_chunks):
        tag = chunk.get("_tag", "")
        tag_part = f" {tag}" if tag else ""
        doc_info = f"Tài liệu [{i+1}]{tag_part} (Số hiệu: {chunk.get('doc_number', 'N/A')}, Tên: {chunk.get('doc_title', 'N/A')}"
        if chunk.get("dieu"):
            doc_info += f", Điều {chunk['dieu']}"
        if chunk.get("khoan"):
            doc_info += f", Khoản {chunk['khoan']}"
        doc_info += ")"
        context_parts.append(f"{doc_info}:\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    # Thêm bối cảnh hội thoại vào system prompt nếu có
    system_content = RAG_QA_PROMPT
    if summary:
        system_content += f"\n\nBối cảnh hội thoại (Ký ức dài hạn): {summary}"

    parser = PydanticOutputParser(pydantic_object=QAResponse)

    # Build messages list: system + history + user
    escaped_system = system_content.replace("{", "{{").replace("}", "}}")
    messages = [("system", escaped_system + "\n\n{format_instructions}")]
    if chat_history:
        for msg in chat_history:
            role = "human" if msg["role"] == "user" else "ai"
            messages.append((role, msg["content"]))
    messages.append(("human", "Context:\n\n{context}\n\n---\n\nCâu hỏi: {question}"))

    prompt = ChatPromptTemplate.from_messages(messages).partial(
        format_instructions=parser.get_format_instructions()
    )
    from langchain_core.output_parsers import StrOutputParser
    import re
    import json

    chain = prompt | model | StrOutputParser()

    try:
        raw_response = chain.invoke({"context": context, "question": question})
        
        # Loại bỏ khối nháp <thought>...</thought>
        cleaned = re.sub(r'<thought>.*?</thought>', '', raw_response, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # Loại bỏ các ký tự code block markdown ```json ... ``` nếu có
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        parsed_data = None
        try:
            parsed_data = json.loads(cleaned)
        except Exception:
            # Thử tìm cặp ngoặc nhọn đầu tiên và cuối cùng nếu bị dính text ngoài
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    parsed_data = json.loads(match.group(0))
                except Exception:
                    pass

        if parsed_data and isinstance(parsed_data, dict):
            citations = []
            raw_citations = parsed_data.get("citations", [])
            for idx, cit in enumerate(raw_citations, 1):
                citations.append({
                    "index": idx,
                    "doc_id": None,
                    "doc_number": cit.get("document_number") or cit.get("doc_number") or "N/A",
                    "doc_title": cit.get("document_name") or cit.get("doc_title") or "N/A",
                    "dieu": cit.get("article") or cit.get("dieu"),
                    "khoan": cit.get("clause") or cit.get("khoan"),
                    "content_preview": cit.get("extracted_text") or cit.get("content_preview") or "",
                })
            
            return {
                "answer": parsed_data.get("answer", ""),
                "citations": citations,
                "model": LLM_MODEL,
                "chunks_used": len(context_chunks),
            }
        else:
            # Nếu không parse được JSON, trả về nội dung text thuần đã làm sạch thought
            return {
                "answer": cleaned,
                "citations": [
                    {
                        "index": i + 1,
                        "doc_id": c.get("document_id"),
                        "doc_number": c.get("doc_number", ""),
                        "doc_title": c.get("doc_title", ""),
                        "dieu": c.get("dieu"),
                        "khoan": c.get("khoan"),
                        "content_preview": c["content"][:200],
                    }
                    for i, c in enumerate(context_chunks)
                ],
                "model": LLM_MODEL,
                "chunks_used": len(context_chunks),
            }
            
    except Exception as e:
        logger.error(f"[AI] generate_qa_answer failed: {e}")
        return {
            "answer": "Xin lỗi, hệ thống AI tạm thời gặp lỗi khi xử lý câu trả lời.",
            "citations": [],
            "model": LLM_MODEL,
            "chunks_used": 0,
        }
