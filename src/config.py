"""
config.py — Cấu hình tập trung cho Phase 2
Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia
"""

import os
from dotenv import load_dotenv

# Load biến môi trường từ file .env nếu có
load_dotenv()

# ─── LLM Configuration ────────────────────────────────────────────────────
# Lấy API keys từ môi trường
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Logic tự động chọn Provider dựa trên Key có sẵn
def detect_provider():
    if GEMINI_API_KEY:
        return "gemini", "gemini/gemini-3.1-flash-lite-preview"
    if OPENAI_API_KEY:
        return "openai", "gpt-4o-mini"
    if ANTHROPIC_API_KEY:
        return "anthropic", "claude-3-haiku-20240307"
    return "ollama", "ollama/vistral" # Mặc định dùng Ollama nếu không có key

LLM_PROVIDER_DETECTED, LLM_MODEL_DETECTED = detect_provider()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", LLM_PROVIDER_DETECTED)
LLM_MODEL = os.getenv("LLM_MODEL", LLM_MODEL_DETECTED)
LLM_API_KEY = OPENAI_API_KEY # litellm dùng biến này cho OpenAI

# ─── Embedding Configuration ──────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bkai-foundation-models/vietnamese-bi-encoder")
EMBEDDING_DIM = 768  # vietnamese-bi-encoder output dimension
EMBEDDING_BATCH_SIZE = 64
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")  # cpu | cuda

# ─── Vector Search ─────────────────────────────────────────────────────────
# Chế độ lưu trữ:
# - 'memory': Lưu trên RAM (mất dữ liệu khi tắt app, phù hợp test nhanh)
# - 'local' : Lưu trên ổ cứng (vĩnh viễn, không phải index lại khi restart)
# - 'server': Kết nối tới Qdrant Server (Docker/Cloud)
QDRANT_MODE = os.getenv("QDRANT_MODE", "local")  # Chuyển sang 'local' để giữ dữ liệu
QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qdrant_data")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = "vanban_chunks"

# ─── Hybrid Search (RRF) ──────────────────────────────────────────────────
RRF_K = 60  # Constant from Cormack et al., 2009
# Trọng số mặc định cho hybrid search
RRF_WEIGHTS = {
    "keyword": {"bm25": 0.8, "vector": 0.2},    # Tra cứu theo số hiệu/tiêu đề
    "semantic": {"bm25": 0.4, "vector": 0.6},    # Tìm quy định liên quan
    "balanced": {"bm25": 0.5, "vector": 0.5},    # Q&A pháp luật
}

# ─── RAG Configuration ────────────────────────────────────────────────────
RAG_TOP_K_RETRIEVE = 20   # Số chunks retrieve trước re-rank
RAG_TOP_K_CONTEXT = 5     # Số chunks dùng làm context cho LLM
RAG_MAX_CONTEXT_TOKENS = 4000
RAG_TEMPERATURE = 0.1     # LLM temperature cho Q&A (chính xác)

# ─── Auto-tagging ─────────────────────────────────────────────────────────
AUTO_TAG_CONFIDENCE_THRESHOLD = 0.85  # Ngưỡng tin cậy để tự động áp dụng tag

LEGAL_FIELDS = [
    "đất đai", "thuế", "lao động", "dân sự", "hình sự",
    "hành chính", "thương mại", "môi trường", "xây dựng",
    "giao thông", "giáo dục", "y tế", "tài chính", "ngân hàng",
    "bảo hiểm", "sở hữu trí tuệ", "đầu tư", "doanh nghiệp",
    "hôn nhân gia đình", "quốc phòng an ninh",
]

# ─── Effectiveness Boosting ───────────────────────────────────────────────
EFFECTIVENESS_BOOST = {
    "con_hieu_luc": 2.0,
    "chua_co_hieu_luc": 1.5,
    "het_hieu_luc_mot_phan": 1.0,
    "het_hieu_luc": 0.3,
}

# ─── Relation Types ──────────────────────────────────────────────────────
RELATION_TYPES = {
    "thay_the": "Thay thế",
    "sua_doi": "Sửa đổi, bổ sung",
    "huong_dan": "Hướng dẫn thi hành",
    "bai_bo": "Bãi bỏ",
    "vien_dan": "Viện dẫn",
    "dinh_chinh": "Đính chính",
}
