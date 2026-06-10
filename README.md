# ⚖️ Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia (DEMOMVP)

Hệ thống tìm kiếm và hỏi đáp pháp luật thông minh sử dụng công nghệ **Hybrid Search** và **RAG (Retrieval-Augmented Generation)**. Dự án được thiết kế để giúp người dùng tra cứu văn bản pháp luật Việt Nam một cách nhanh chóng, chính xác và có khả năng trả lời các câu hỏi pháp lý dựa trên ngữ cảnh thực tế, đồng thời tạo tự động các biểu mẫu hành chính.

---

## 🚀 Tính năng nổi bật (Phase 2 Nâng cấp)

- **🔍 Hybrid Search & Hierarchy-Aware Boosting**: Tìm kiếm kết hợp BM25 và Vector Search (Qdrant). Đặc biệt hỗ trợ nhân trọng số điểm dựa trên cấp bậc pháp lý (Hiến pháp > Luật > Nghị định...) và ưu tiên văn bản mới ban hành.
- **🤖 Strict RAG Q&A (Chống Hallucination)**: Hệ thống hỏi đáp pháp luật thông minh, được trang bị *Mega Prompts* nghiêm ngặt với luật lệ xử lý các trường hợp văn bản hết hiệu lực, mâu thuẫn luật và từ chối đoán mò khi thiếu ngữ cảnh.
- **📄 Tạo văn bản hành chính tự động (Document Generator)**: Trích xuất thông tin hội thoại bằng AI để điền tự động vào các biểu mẫu hành chính (Đơn khiếu nại, Tờ trình, Công văn). Hỗ trợ xuất trực tiếp ra PDF, DOCX và Markdown.
- **💬 Quản lý Phiên hội thoại**: Tính năng chat giống ChatGPT với trí nhớ dài hạn, tóm tắt nội dung các cuộc trò chuyện tự động bằng AI.
- **🔗 Legal Relations (Context Expansion)**: Tự động phát hiện mối quan hệ giữa các văn bản (Thay thế, Sửa đổi, Hướng dẫn). Khi hỏi về một Luật, hệ thống tự động tìm thêm Nghị định/Thông tư hướng dẫn để mở rộng ngữ cảnh RAG.
- **⚡ API Sẵn sàng với Postman**: Cung cấp sẵn bộ `DEMOMVP_Postman_Collection.json` để dễ dàng test các API tìm kiếm, Q&A, quản lý lịch sử chat và sinh file PDF.

---

## 🏗️ Cấu trúc dự án

```text
DEMOMVP/
├── src/
│   ├── core/           # Bộ não: AI Service, Strict RAG Engine, Vector Search
│   ├── database/       # Dữ liệu: SQLite Setup, Models, Schema
│   ├── services/       # Logic phụ trợ: Doc Generator (Sinh PDF/DOCX), Chat Sessions
│   └── config.py       # Cấu hình tập trung (Model, API Key)
├── templates/          # Giao diện Server-side Rendering (Jinja2)
│   ├── index.html      # Trang chủ (Hybrid Search)
│   ├── qa.html         # Trang Hỏi đáp AI & Sinh biểu mẫu hành chính
│   └── doc_templates/  # Các mẫu biểu mẫu hành chính (Markdown)
├── prompts/            # Thư mục chứa Mega Prompts cấu trúc JSON (Zero-hallucination)
├── data/               # Thư mục nạp văn bản đầu vào (.json, .txt)
├── drafts/             # Thư mục lưu trữ tạm các văn bản Word/PDF được AI sinh ra
├── main.py             # Entry point FastAPI
└── DEMOMVP_Postman...  # File cấu hình Postman API
```

---

## 🛠️ Công nghệ sử dụng

- **Backend**: FastAPI (Python 3.11+)
- **Database & Search**: SQLite (BM25) & Qdrant Vector DB
- **LLM Engine**: LiteLLM (Hỗ trợ Google Gemini, Claude, OpenAI)
- **Document Processing**: `python-docx`, `soffice` (LibreOffice) để convert Markdown -> DOCX -> PDF.
- **Frontend**: HTML5, Vanilla JS, CSS (Giao diện Glassmorphism hiện đại).

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
Tạo file `.env` ở thư mục gốc và cung cấp API key (Ưu tiên các mô hình mạnh về suy luận như Claude 3.5 Sonnet hoặc Gemini 1.5 Pro):
```env
GEMINI_API_KEY=your_gemini_api_key_here
ANTHROPIC_API_KEY=your_claude_api_key_here
```

### 4. Khởi chạy ứng dụng
```bash
python main.py
```
*Giao diện Tìm kiếm:* `http://localhost:8000`
*Giao diện Hỏi đáp AI:* `http://localhost:8000/qa`

---

## 📖 Hướng dẫn sử dụng tính năng mới

1. **Hỏi đáp Strict RAG**: Vào `/qa`, đặt một câu hỏi pháp lý. Nếu câu hỏi mơ hồ, AI sẽ yêu cầu làm rõ. Nếu hỏi ngoài luồng, AI sẽ từ chối trả lời.
2. **Sinh Biểu mẫu Hành chính**: Ngay dưới mỗi câu trả lời tư vấn của AI, chọn loại biểu mẫu (Ví dụ: Đơn khiếu nại) và bấm "Tạo văn bản". Bạn có thể tải ngay file PDF hoặc Word hoàn chỉnh.
3. **Test API qua Postman**: Import file `DEMOMVP_Postman_Collection.json` vào Postman. Chạy thư mục `Hỏi đáp RAG & Chat History` để thử nghiệm flow gọi AI và tạo file qua API.

---

## 🛡️ Giấy phép
Dự án được phát triển cho mục đích Demo/MVP. Toàn bộ mã nguồn được bảo mật theo yêu cầu cá nhân.
