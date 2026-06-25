"""
guard_nodes.py — LangGraph Nodes thay thế các block lặp lại trong system_prompt.py
Phiên bản: v1.0

Các Node trong file này xử lý TRƯỚC khi LLM chính nhận prompt, thay thế cho:
  1. SecurityGuardNode  ← thay block "CHỈ THỊ PHÒNG THỦ ĐỐI KHÁNG" (5 lần lặp, ~800 tokens)
                          + Ví dụ 6 (không xác nhận) + Ví dụ 7 (injection) trong RAG few-shot
  2. IntentRouterNode   ← thay phân loại SMALL_TALK / OUT_OF_SCOPE trong RAG
                          + Ví dụ 8 (small talk) + Ví dụ 9 (out of scope)
  3. TextNormalizerNode ← thay block "CHUYỂN ĐỔI VĂN PHONG" trong DOC_EXTRACTION_PROMPT

Tích hợp vào rag_engine.py:
    graph.add_node("security_guard", security_guard_node)
    graph.add_node("intent_router", intent_router_node)
    graph.set_entry_point("security_guard")
    graph.add_edge("security_guard", "intent_router")
    graph.add_conditional_edges("intent_router", _route_by_intent, {
        "rag": "load_session",
        "small_talk": "small_talk_response",
        "out_of_scope": "out_of_scope_response",
        "blocked": "blocked_response",
    })
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# 1. SECURITY GUARD NODE
# Thay thế toàn bộ block "CHỈ THỊ PHÒNG THỦ ĐỐI KHÁNG" trong 4 prompts.
# Chạy TRƯỚC khi vào bất kỳ LLM nào. Chi phí: 0 token (pure Python regex).
# =============================================================================

# Các pattern nhận diện jailbreak / injection
_JAILBREAK_PATTERNS = [
    r"\bignore\s+(previous|all|your)\s+instructions?\b",
    r"\bforget\s+(your|all|previous)\b",
    r"\bact\s+as\b",
    r"\bpretend\s+(you\s+are|to\s+be)\b",
    r"\bdeveloper\s+mode\b",
    r"\bdan\b",          # DAN jailbreak
    r"\bsudo\b",
    r"\boverride\b",
    r"\bjailbreak\b",
    r"bỏ\s+qua\s+quy\s+tắc",
    r"bỏ\s+qua\s+hướng\s+dẫn",
    r"bỏ\s+qua\s+tất\s+cả",
    r"không\s+cần\s+trích\s+dẫn",
    r"đóng\s+vai\s+(luật\s+sư|thẩm\s+phán|chuyên\s+gia)",
    r"tiết\s+lộ\s+system\s+prompt",
    r"in\s+lại\s+system\s+prompt",
    r"cho\s+tôi\s+biết\s+(cấu\s+hình|prompt\s+hệ\s+thống)",
    # Prompt injection nhúng trong document (thường đến từ context)
    r"AI[,:]?\s*(hãy|vui\s+lòng)?\s*bỏ\s+qua",
    r"\[SYSTEM\]",
    r"<system>",
]

_JAILBREAK_RE = re.compile("|".join(_JAILBREAK_PATTERNS), re.IGNORECASE | re.UNICODE)

# Confirmation attack: user yêu cầu xác nhận thông tin pháp lý tự đặt ra
_CONFIRMATION_ATTACK_PATTERNS = [
    r"(điều\s+\w+|khoản\s+\w+).*(quy\s+định|nêu\s+rõ|ghi\s+là).*(xác\s+nhận|đúng\s+không|phải\s+không)",
    r"(tôi\s+biết|tôi\s+hiểu).*(xác\s+nhận|confirm)\s+(giúp|cho)\s+tôi",
    r"xác\s+nhận\s+(giúp|hộ|cho)\s+tôi.*điều\s+\w+",
]
_CONFIRMATION_RE = re.compile("|".join(_CONFIRMATION_ATTACK_PATTERNS), re.IGNORECASE | re.UNICODE)

# System prompt leak detection
_LEAK_PATTERNS = [
    r"(system\s+prompt|system\s+instruction|cấu\s+hình\s+hệ\s+thống)",
    r"(bạn\s+được\s+lập\s+trình|bạn\s+hoạt\s+động\s+như\s+thế\s+nào)",
    r"(print|show|display|reveal).*(system|prompt|instruction)",
]
_LEAK_RE = re.compile("|".join(_LEAK_PATTERNS), re.IGNORECASE | re.UNICODE)


def detect_security_threat(text: str) -> Optional[str]:
    """
    Phát hiện mối đe dọa bảo mật trong input.
    Returns:
        None — an toàn, cho phép tiếp tục
        "jailbreak" — phát hiện jailbreak/injection
        "confirmation_attack" — yêu cầu xác nhận sai
        "leak" — yêu cầu tiết lộ system prompt
    """
    if not text:
        return None
    if _JAILBREAK_RE.search(text):
        return "jailbreak"
    if _CONFIRMATION_RE.search(text):
        return "confirmation_attack"
    if _LEAK_RE.search(text):
        return "leak"
    return None


def security_guard_node(state: dict) -> dict:
    """
    LangGraph Node: SecurityGuard — Phát hiện jailbreak / injection / leak.

    Thay thế cho block "CHỈ THỊ PHÒNG THỦ ĐỐI KHÁNG" trong tất cả prompts.
    Chi phí: 0 token (pure Python, không gọi LLM).

    State fields đọc: "question"
    State fields ghi: "threat_type", "blocked", "answer" (nếu bị chặn), "citations"
    """
    question = state.get("question", "")
    threat = detect_security_threat(question)

    if threat:
        logger.warning(f"[SecurityGuard] Threat detected: {threat} | question[:80]: {question[:80]}")
        state["threat_type"] = threat
        state["blocked"] = True

        if threat == "leak":
            state["answer"] = "Tôi là hệ thống tra cứu pháp luật Việt Nam. Tôi không thể chia sẻ thông tin cấu hình hệ thống."
        else:
            # jailbreak hoặc confirmation_attack
            state["answer"] = "Tôi không tìm thấy căn cứ pháp lý phù hợp trong cơ sở dữ liệu hiện tại để trả lời câu hỏi này."
        state["citations"] = []
        state["chunks_used"] = 0
    else:
        state["blocked"] = False
        state["threat_type"] = None

    return state


# =============================================================================
# 2. INTENT ROUTER NODE
# Thay thế phân loại SMALL_TALK / OUT_OF_SCOPE + Ví dụ 8-9 trong RAG_QA_PROMPT.
# Chạy sau SecurityGuard, trước RAG pipeline.
# Chi phí: ~0 token (keyword matching) — chỉ gọi LLM khi không match được.
# =============================================================================

# Từ khóa nhận diện small talk
_SMALL_TALK_KEYWORDS = [
    r"\bxin\s+chào\b", r"\bchào\s+(bạn|anh|chị|em)\b", r"\bhello\b", r"\bhi\b",
    r"\bcảm\s+ơn\b", r"\bthank\b", r"\btạm\s+biệt\b", r"\bbye\b", r"\bgoodbye\b",
    r"\bbạn\s+(có\s+khỏe|tên\s+là|là\s+ai|làm\s+gì)\b",
    r"\bhôm\s+nay\s+thế\s+nào\b",
    r"\bgiới\s+thiệu\s+(về\s+)?bản\s+thân\b",
]

# Từ khóa nhận diện out of scope (không liên quan pháp luật Việt Nam)
_OUT_OF_SCOPE_KEYWORDS = [
    # Lập trình / kỹ thuật
    r"\bcode\b", r"\bpython\b", r"\bjavascript\b", r"\bsql\b", r"\blập\s+trình\b",
    # Y tế / sức khỏe không liên quan pháp lý
    r"\bchữa\s+bệnh\b", r"\bthuốc\s+gì\b", r"\bbác\s+sĩ\b",
    # Ẩm thực
    r"\bnấu\s+ăn\b", r"\bcông\s+thức\s+nấu\b",
    # Thể thao / giải trí
    r"\bbóng\s+đá\b", r"\bkết\s+quả\s+(trận|bóng)\b",
    # Địa lý / du lịch thuần túy
    r"\bthời\s+tiết\b", r"\bdu\s+lịch\b.*\bnên\s+đi\b",
    # Ngoại ngữ
    r"\bdịch\s+(sang|qua)\s+(tiếng\s+(anh|nhật|hàn|trung))\b",
]

_SMALL_TALK_RE = re.compile("|".join(_SMALL_TALK_KEYWORDS), re.IGNORECASE | re.UNICODE)
_OUT_OF_SCOPE_RE = re.compile("|".join(_OUT_OF_SCOPE_KEYWORDS), re.IGNORECASE | re.UNICODE)

# Từ khóa pháp luật — nếu có, ưu tiên route sang RAG dù match small_talk/out_of_scope
_LEGAL_SIGNAL_KEYWORDS = [
    r"\bpháp\s+luật\b", r"\bquy\s+định\b", r"\bnghị\s+định\b", r"\bthông\s+tư\b",
    r"\bluật\b", r"\bđiều\s+\d+\b", r"\bkhoản\b", r"\bxử\s+phạt\b", r"\bvi\s+phạm\b",
    r"\bhợp\s+đồng\b", r"\btòa\s+án\b", r"\bkhiếu\s+nại\b", r"\btố\s+cáo\b",
    r"\bquyền\b", r"\bnghĩa\s+vụ\b", r"\bchế\s+tài\b", r"\bmức\s+phạt\b",
    r"\bgiấy\s+phép\b", r"\bđăng\s+ký\b", r"\bthủ\s+tục\b",
]
_LEGAL_SIGNAL_RE = re.compile("|".join(_LEGAL_SIGNAL_KEYWORDS), re.IGNORECASE | re.UNICODE)


def classify_intent(question: str) -> str:
    """
    Phân loại intent bằng keyword matching (0 token).
    Returns: "rag" | "small_talk" | "out_of_scope"
    """
    if not question or len(question.strip()) < 3:
        return "small_talk"

    # Nếu có tín hiệu pháp luật rõ ràng → route thẳng vào RAG
    if _LEGAL_SIGNAL_RE.search(question):
        return "rag"

    # Kiểm tra small talk
    if _SMALL_TALK_RE.search(question) and len(question.split()) <= 15:
        return "small_talk"

    # Kiểm tra out of scope
    if _OUT_OF_SCOPE_RE.search(question):
        return "out_of_scope"

    # Mặc định: thử RAG
    return "rag"


def intent_router_node(state: dict) -> dict:
    """
    LangGraph Node: IntentRouter — Phân loại câu hỏi trước khi vào RAG.

    Thay thế cho:
    - Phân loại SMALL_TALK / OUT_OF_SCOPE trong RAG_QA_PROMPT
    - Few-shot Ví dụ 8 và 9 trong RAG_QA_PROMPT
    Chi phí: 0 token (keyword matching).

    State fields đọc: "question", "blocked"
    State fields ghi: "intent"
    """
    # Nếu đã bị SecurityGuard chặn → không cần phân loại
    if state.get("blocked"):
        state["intent"] = "blocked"
        return state

    question = state.get("question", "")
    intent = classify_intent(question)
    state["intent"] = intent

    logger.info(f"[IntentRouter] intent={intent} | question[:60]: {question[:60]}")
    return state


def _route_by_intent(state: dict) -> str:
    """
    LangGraph conditional edge: route dựa trên intent.
    Trả về key tương ứng với mapping của conditional edges.
    """
    if state.get("blocked"):
        return "blocked_response"
    intent = state.get("intent", "rag")
    if intent == "small_talk":
        return "small_talk"
    if intent == "out_of_scope":
        return "out_of_scope"
    return "load_session"  # → RAG pipeline


def small_talk_response_node(state: dict) -> dict:
    """Node: trả lời ngay cho small talk, không gọi LLM."""
    state.update({
        "answer": "Xin chào! Tôi là hệ thống tra cứu pháp luật Việt Nam. Bạn cần tra cứu vấn đề pháp luật nào?",
        "citations": [],
        "chunks_used": 0,
        "model": "rule-based",
        "ai_available": True,
    })
    return state


def out_of_scope_response_node(state: dict) -> dict:
    """Node: trả lời ngay cho câu hỏi ngoài phạm vi, không gọi LLM."""
    state.update({
        "answer": "Xin lỗi, tôi chỉ hỗ trợ tra cứu pháp luật Việt Nam. Vui lòng đặt câu hỏi liên quan đến quy định pháp luật.",
        "citations": [],
        "chunks_used": 0,
        "model": "rule-based",
        "ai_available": True,
    })
    return state


def blocked_response_node(state: dict) -> dict:
    """Node: trả về response đã được SecurityGuard chuẩn bị (không làm gì thêm)."""
    # answer đã được set bởi security_guard_node
    state.setdefault("model", "rule-based")
    state.setdefault("ai_available", True)
    return state


# =============================================================================
# 3. TEXT NORMALIZER NODE
# Thay thế block "CHUYỂN ĐỔI VĂN PHONG" trong DOC_EXTRACTION_PROMPT.
# Chạy trước DOC_EXTRACTION để chuẩn hóa ngôn ngữ khẩu ngữ → hành chính pháp lý.
# Chi phí: 1 LLM call nhỏ (model nhanh/rẻ) thay vì nhúng examples vào prompt chính.
# =============================================================================

TEXT_NORMALIZER_PROMPT = """Bạn là công cụ chuẩn hóa văn phong pháp lý. Nhiệm vụ duy nhất: chuyển đổi câu khẩu ngữ/cảm xúc → văn phong hành chính pháp lý trung lập.

Nguyên tắc:
- Loại bỏ cảm xúc, tiếng lóng, từ xưng hô thân mật.
- Dùng thuật ngữ pháp lý chính xác.
- Mô tả hành vi khách quan.
- Xác định rõ quan hệ pháp lý các bên (NSDLĐ/NLĐ, bên mua/bên bán, vợ/chồng...).
- Giữ nguyên các thông tin định danh (họ tên, ngày tháng, số tiền, địa chỉ).
- Nếu câu đã đúng văn phong hành chính → trả nguyên văn, không sửa.

Ví dụ:
Input: "lão giám đốc tự nhiên đuổi việc tôi không báo trước"
Output: "NSDLĐ đã đơn phương chấm dứt HĐLĐ trái pháp luật và không thực hiện nghĩa vụ báo trước theo quy định."

Input: "công ty quỵt tiền hàng rồi trốn mất"
Output: "Bên mua vi phạm nghĩa vụ thanh toán theo hợp đồng và có dấu hiệu trốn tránh thực hiện nghĩa vụ tài chính."

Input: "cơ quan đó để hồ sơ lơ lửng mấy tháng không chịu giải quyết"
Output: "Cơ quan có thẩm quyền chưa giải quyết hồ sơ trong thời hạn quy định, gây ảnh hưởng đến quyền và lợi ích hợp pháp của người nộp hồ sơ."

Chỉ trả về đoạn văn đã chuẩn hóa — KHÔNG giải thích, KHÔNG thêm gì khác."""


def text_normalizer_node(state: dict) -> dict:
    """
    LangGraph Node: TextNormalizer — Chuẩn hóa văn phong hội thoại trước khi trích xuất.

    Thay thế cho block "CHUYỂN ĐỔI VĂN PHONG" trong DOC_EXTRACTION_PROMPT.
    Chỉ áp dụng khi pipeline là DOC_EXTRACTION.
    Dùng model nhỏ/rẻ (temperature=0, max_tokens=500) để tiết kiệm chi phí.

    State fields đọc: "conversation_text", "skip_normalize" (optional)
    State fields ghi: "normalized_conversation"
    """
    # Nếu đã đánh dấu bỏ qua normalize (vd: văn bản đã chuẩn)
    if state.get("skip_normalize"):
        state["normalized_conversation"] = state.get("conversation_text", "")
        return state

    conversation_text = state.get("conversation_text", "")
    if not conversation_text or len(conversation_text.strip()) < 10:
        state["normalized_conversation"] = conversation_text
        return state

    try:
        from src.core.ai_service import _get_chat_model
        # Dùng model nhanh/rẻ nhất có thể, max_tokens nhỏ
        model = _get_chat_model(temperature=0.0, max_tokens=500)
        if not model:
            state["normalized_conversation"] = conversation_text
            return state

        response = model.invoke([
            ("system", TEXT_NORMALIZER_PROMPT),
            ("human", conversation_text),
        ])
        normalized = response.content if hasattr(response, "content") else str(response)
        state["normalized_conversation"] = normalized.strip()
        logger.info(f"[TextNormalizer] Normalized {len(conversation_text)} → {len(normalized)} chars")
    except Exception as e:
        logger.warning(f"[TextNormalizer] Failed, using original: {e}")
        state["normalized_conversation"] = conversation_text

    return state
