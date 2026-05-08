# ⚖️ Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia (DEMOMVP)

Hệ thống tìm kiếm và hỏi đáp pháp luật thông minh sử dụng công nghệ **Hybrid Search** và **RAG (Retrieval-Augmented Generation)**. Dự án được thiết kế để giúp người dùng tra cứu văn bản pháp luật Việt Nam một cách nhanh chóng, chính xác và có khả năng trả lời các câu hỏi pháp lý dựa trên ngữ cảnh thực tế.

---

## 🚀 Tính năng nổi bật (Phase 2)

- **🔍 Hybrid Search**: Kết hợp sức mạnh của tìm kiếm từ khóa truyền thống (BM25 - SQLite FTS5) và tìm kiếm ngữ nghĩa (Semantic Search - Qdrant Vector Database).
- **🤖 RAG Q&A**: Hệ thống hỏi đáp pháp luật thông minh. AI (Gemini/GPT) sẽ trả lời dựa trên các đoạn trích dẫn thực tế từ cơ sở dữ liệu văn bản đã nạp.
- **🔗 Legal Relations**: Tự động phát hiện mối quan hệ giữa các văn bản (Thay thế, Sửa đổi, Hướng dẫn, Viện dẫn...) bằng Regex và LLM.
- **📝 Auto Summarization & Tagging**: Tự động tóm tắt nội dung văn bản và gán nhãn lĩnh vực pháp lý (Đất đai, Thuế, Lao động...).
- **⚡ Optimized Processing**: Cơ chế xử lý song song, hỗ trợ lưu trữ vector bền vững (Persistence) và khả năng tiếp tục xử lý (Resume) sau khi restart.

---

## 🏗️ Cấu trúc dự án

Dự án được tổ chức theo cấu trúc package hiện đại, sạch sẽ:

```text
DEMOMVP/
├── src/
│   ├── core/           # Bộ não: AI Service, Embedding, RAG Engine, Vector Search
│   ├── database/       # Dữ liệu: SQLite Setup, Models, Schema
│   ├── services/       # Xử lý logic: Ingestion, Legal Relations, Search
│   └── config.py       # Cấu hình tập trung (Model, API Key, Paths)
├── static/             # Assets: CSS, JS, Images
├── templates/          # Giao diện Jinja2 (Search Portal, Q&A, Document Detail)
├── data/               # Folder chứa dữ liệu văn bản đầu vào
├── main.py             # Entry point để khởi chạy ứng dụng FastAPI
├── .env                # Biến môi trường (API Keys)
└── requirements.txt    # Danh sách các thư viện cần thiết
```

---

## 🛠️ Công nghệ sử dụng

- **Backend**: FastAPI (Python 3.11+)
- **Vector Database**: Qdrant (Local Persistent Mode)
- **Search Engine**: SQLite FTS5 (BM25 Ranking)
- **LLM**: Google Gemini (thông qua LiteLLM)
- **Embeddings**: Vietnamese Bi-Encoder (`bkai-foundation-models/vietnamese-bi-encoder`)
- **Frontend**: Vanilla JS, CSS, Jinja2 Templates

---

## 📦 Cài đặt & Khởi chạy

### 1. Clone dự án
```bash
git clone https://github.com/dungna13/DEMOMVP.git
cd DEMOMVP
```

### 2. Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 3. Cấu hình môi trường
Tạo file `.env` ở thư mục gốc và thêm API Key của bạn:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 4. Khởi chạy ứng dụng
```bash
python main.py
```
Ứng dụng sẽ khả dụng tại: `http://localhost:8000`

---

## 📖 Hướng dẫn sử dụng

1. **Nạp dữ liệu**: Đặt các file JSON văn bản vào thư mục `chunks/` hoặc `data/`. Hệ thống sẽ tự động nạp và đánh chỉ mục khi khởi động.
2. **Tìm kiếm**: Nhập số hiệu văn bản hoặc nội dung cần tìm tại trang chủ.
3. **Hỏi đáp AI**: Chuyển sang mục **Hỏi đáp (QA)** để đặt câu hỏi tự nhiên về quy định pháp luật.
4. **Xem chi tiết**: Click vào từng văn bản để xem nội dung đầy đủ, bản tóm tắt và sơ đồ quan hệ pháp lý liên quan.

---

## 🛡️ Giấy phép
Dự án được phát triển cho mục đích Demo/MVP. Toàn bộ mã nguồn được bảo mật theo yêu cầu cá nhân.
