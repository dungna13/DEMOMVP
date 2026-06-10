"""
chat_service.py — Dịch vụ quản lý phiên trò chuyện và bộ nhớ RAG (Short-term & Long-term memory)
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from src.database.database import get_db

logger = logging.getLogger(__name__)


def create_chat_session(session_id: Optional[str] = None, user_id: str = "default_user") -> str:
    """Tạo mới một phiên trò chuyện (chat session)."""
    if not session_id:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (session_id, user_id, created_at, updated_at, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, now_str, now_str, None)
        )
    logger.info(f"[ChatService] Created chat session: {session_id} for user {user_id}")
    return session_id


def get_chat_sessions(user_id: str = "default_user") -> List[Dict[str, Any]]:
    """Lấy danh sách toàn bộ các phiên trò chuyện của một user."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT session_id, user_id, created_at, updated_at, summary
            FROM chat_sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,)
        ).fetchall()
        
        sessions = []
        for r in rows:
            sessions.append({
                "session_id": r["session_id"],
                "user_id": r["user_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "summary": r["summary"]
            })
        return sessions


def get_session_detail(session_id: str) -> Optional[Dict[str, Any]]:
    """Lấy chi tiết thông tin một session."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_id, user_id, created_at, updated_at, summary FROM chat_sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def delete_chat_session(session_id: str) -> bool:
    """Xóa một phiên trò chuyện và các tin nhắn đi kèm (cascade)."""
    try:
        with get_db() as conn:
            # SQLite ON DELETE CASCADE sẽ tự xóa chat_messages nếu khóa ngoại được kích hoạt.
            # Để chắc chắn, ta xóa cả hai bảng.
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            success = cursor.rowcount > 0
        logger.info(f"[ChatService] Deleted chat session: {session_id}, success: {success}")
        return success
    except Exception as e:
        logger.error(f"[ChatService] Error deleting session {session_id}: {e}")
        return False


def save_chat_message(session_id: str, role: str, content: str, tokens_used: int = 0) -> str:
    """Lưu tin nhắn mới vào database và cập nhật thời gian cập nhật của phiên."""
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Kiểm tra và tạo session TRƯỚC khi mở get_db() — tránh deadlock nested context
    session_detail = get_session_detail(session_id)
    if not session_detail:
        create_chat_session(session_id=session_id)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (message_id, session_id, role, content, timestamp, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, now_str, tokens_used)
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            (now_str, session_id)
        )

    logger.debug(f"[ChatService] Saved message {message_id} ({role}) in session {session_id}")
    return message_id


def get_chat_messages(session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách các tin nhắn trong phiên, sắp xếp theo thời gian tăng dần."""
    query = """
        SELECT message_id, session_id, role, content, timestamp, tokens_used
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
    """
    params = [session_id]
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
        
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        messages = []
        for r in rows:
            messages.append({
                "message_id": r["message_id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "timestamp": r["timestamp"],
                "tokens_used": r["tokens_used"]
            })
        return messages


# Lưu số lượng tin nhắn đã tóm tắt lần cuối, tránh gọi LLM dư thừa
_summarize_thresholds: dict = {}


def summarize_session_if_needed(session_id: str) -> Optional[str]:
    """
    Kiểm tra và cập nhật tóm tắt phiên hội thoại (Trí nhớ dài hạn).
    Chỉ kích hoạt LLM khi số lượng tin nhắn tăng thêm ít nhất 4 so với lần tóm tắt trước.
    """
    try:
        messages = get_chat_messages(session_id)
        msg_count = len([m for m in messages if m["role"] in ("user", "assistant")])

        # Ngưỡng tối thiểu: 4 tin nhắn mới bắt đầu tóm tắt
        if msg_count < 4:
            return None

        # Kiểm tra xem có đủ tin nhắn MỚI kể từ lần tóm tắt trước không
        last_count = _summarize_thresholds.get(session_id, 0)
        
        # Nếu chưa ghi nhận threshold trong phiên chạy này nhưng DB đã có summary,
        # khởi tạo threshold bằng msg_count - 2 để tránh re-summarize thừa khi restart server
        if session_id not in _summarize_thresholds:
            session_detail = get_session_detail(session_id)
            if session_detail and session_detail.get("summary"):
                last_count = max(0, msg_count - 2)
                _summarize_thresholds[session_id] = last_count

        # Chỉ re-summarize khi có ít nhất 4 tin nhắn mới kể từ lần tóm tắt trước
        if msg_count - last_count < 4:
            return None

        # Định dạng lịch sử để gửi cho LLM tóm tắt
        chat_str = ""
        for m in messages:
            sender = "Người dùng" if m["role"] == "user" else "Trợ lý AI"
            # Giới hạn độ dài mỗi lượt để tránh vượt token limit
            content_preview = m['content'][:300]
            chat_str += f"{sender}: {content_preview}\n"

        from src.core.ai_service import _call_llm

        system_prompt = """Bạn là trợ lý ảo phân tích hội thoại pháp luật Việt Nam.
Nhiệm vụ của bạn là viết một bản tóm tắt cực kỳ ngắn gọn, cô đọng (1-2 câu, dưới 100 từ) về nhu cầu, bối cảnh pháp lý hoặc các vấn đề chính mà người dùng đang tìm kiếm và được tư vấn trong cuộc hội thoại này.
Ví dụ: "Người dùng đang tìm hiểu điều kiện nhận chuyển nhượng đất trồng lúa và hạn mức nhận chuyển quyền tại Long An."
Hãy trả về trực tiếp nội dung tóm tắt, không thêm bất kỳ văn bản dẫn dắt hay tiêu đề nào."""

        messages_payload = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Lịch sử cuộc hội thoại:\n{chat_str}\n\nTóm tắt:"}
        ]

        summary = _call_llm(messages_payload, temperature=0.3, max_tokens=150)

        if summary:
            summary = summary.strip()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # ← Fix: dùng đúng %H:%M:%S
            with get_db() as conn:
                conn.execute(
                    "UPDATE chat_sessions SET summary = ?, updated_at = ? WHERE session_id = ?",
                    (summary, now_str, session_id)
                )
            # Cập nhật ngưỡng đã tóm tắt
            _summarize_thresholds[session_id] = msg_count
            logger.info(f"[ChatService] Updated long-term memory for session {session_id} ({msg_count} msgs): {summary}")
            return summary

    except Exception as e:
        logger.error(f"[ChatService] Failed to summarize session {session_id}: {e}")

    return None
