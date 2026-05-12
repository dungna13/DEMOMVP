<div style="text-align: center; padding: 120px 0 60px 0;">

# Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia

## Tài liệu Thiết kế Tổng thể (High-Level Design)

**Phiên bản:** 1.0
**Ngày:** 05/05/2026
**Trạng thái:** Draft

</div>

<div style="page-break-after: always;"></div>

## Lịch sử thay đổi

| Phiên bản | Ngày       | Tác giả | Mô tả                |
|-----------|------------|---------|----------------------|
| 1.0       | 05/05/2026 |         | Bản draft đầu tiên   |

<div style="page-break-after: always;"></div>

## Mục lục

1. [Giới thiệu](#1-giới-thiệu)
2. [Phạm vi hệ thống](#2-phạm-vi-hệ-thống)
3. [Kiến trúc tổng thể](#3-kiến-trúc-tổng-thể)
4. [Mô tả các thành phần](#4-mô-tả-các-thành-phần)
5. [Luồng dữ liệu chính](#5-luồng-dữ-liệu-chính)
6. [Mô hình dữ liệu](#6-mô-hình-dữ-liệu)
7. [Chiến lược tìm kiếm](#7-chiến-lược-tìm-kiếm)
8. [Tích hợp AI](#8-tích-hợp-ai)
9. [Knowledge Wiki (Obsidian)](#9-knowledge-wiki-obsidian)
10. [Yêu cầu phi chức năng](#10-yêu-cầu-phi-chức-năng)
11. [Công nghệ sử dụng](#11-công-nghệ-sử-dụng)
12. [Lộ trình triển khai](#12-lộ-trình-triển-khai)
13. [Phụ lục](#13-phụ-lục)

<div style="page-break-after: always;"></div>

## 1. Giới thiệu

### 1.1. Mục đích tài liệu

Tài liệu này mô tả thiết kế tổng thể (High-Level Design) của **Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia** — một nền tảng số hóa, tìm kiếm, và khai thác tri thức từ kho văn bản pháp luật và hành chính của Việt Nam. Tài liệu nhằm mục đích:

- Trình bày kiến trúc hệ thống và các thành phần chính
- Mô tả luồng dữ liệu và tương tác giữa các thành phần
- Làm rõ cách tích hợp Obsidian (admin wiki IDE) và RAG (tìm kiếm & hỏi đáp)
- Cung cấp cơ sở cho việc đánh giá và phê duyệt trước khi triển khai chi tiết

### 1.2. Đối tượng đọc

- Lãnh đạo cơ quan (phê duyệt thiết kế)
- Đội phát triển (triển khai)
- Cán bộ pháp chế (kiểm tra tính đúng đắn nghiệp vụ)
- QA (xây dựng kế hoạch kiểm thử)

### 1.3. Tổng quan hệ thống

Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia là một nền tảng phục vụ cán bộ công chức, chuyên viên pháp chế, luật sư, và công dân tra cứu, tìm kiếm, và khai thác tri thức từ kho **văn bản quy phạm pháp luật** (VBQPPL) và **văn bản hành chính** của Việt Nam. Hệ thống cung cấp:

- **Thu thập & chuẩn hóa**: Nhập văn bản từ nhiều nguồn (Công báo, cổng thông tin Chính phủ, Bộ Tư pháp, HĐND/UBND các cấp), tự động trích xuất nội dung và metadata theo cấu trúc pháp lý
- **Tìm kiếm thông minh**: Kết hợp full-text search (BM25) và vector search cho kết quả chính xác cả về thuật ngữ pháp lý lẫn ngữ nghĩa
- **Tra cứu quan hệ pháp lý**: Theo dõi hiệu lực, thay thế, sửa đổi bổ sung, hướng dẫn thi hành giữa các văn bản
- **Hỏi đáp pháp luật (RAG)**: Trả lời câu hỏi về quy định pháp luật với trích dẫn chính xác đến điều khoản, văn bản gốc
- **Knowledge Wiki (Obsidian)**: Biên dịch tri thức pháp luật thành wiki có cấu trúc, do LLM duy trì — admin biên tập qua Obsidian như một "IDE pháp lý"

<div style="page-break-after: always;"></div>

## 2. Phạm vi hệ thống

### 2.1. Loại văn bản trong phạm vi

| Loại văn bản                  | Ví dụ                                                         | Ưu tiên  |
|-------------------------------|---------------------------------------------------------------|----------|
| Luật, Bộ luật                 | Luật Đất đai 2024, Bộ luật Dân sự 2015                       | Cao      |
| Pháp lệnh                    | Pháp lệnh Ưu đãi người có công                                | Cao      |
| Nghị định                     | Nghị định 43/2014/NĐ-CP                                       | Cao      |
| Thông tư                      | Thông tư 36/2023/TT-BTC                                       | Cao      |
| Quyết định (QPPL)            | Quyết định 15/2020/QĐ-TTg                                     | Trung bình |
| Nghị quyết (HĐND)            | Nghị quyết HĐND tỉnh/thành phố                                | Trung bình |
| Công văn, Chỉ thị            | Công văn hướng dẫn, Chỉ thị của Thủ tướng                     | Thấp     |
| Án lệ, Bản án                | Án lệ của TANDTC, Bản án hành chính                            | Thấp     |

### 2.2. Nguồn dữ liệu

| Nguồn                         | Định dạng                | Phương thức thu thập       |
|--------------------------------|--------------------------|---------------------------|
| Công báo nước CHXHCN Việt Nam | HTML, PDF                | Crawl định kỳ + API       |
| Cổng thông tin Chính phủ       | HTML                     | Crawl định kỳ             |
| Cơ sở dữ liệu quốc gia về VBQPPL (vbpl.vn) | HTML, XML  | API / Crawl               |
| Cổng thông tin Bộ Tư pháp     | HTML, PDF                | Crawl định kỳ             |
| HĐND/UBND các tỉnh/thành phố  | PDF, DOC, HTML           | Crawl + gửi trực tiếp     |
| Công báo tỉnh/thành phố       | PDF                      | Upload thủ công / Crawl   |

### 2.3. Quy mô

| Chỉ số                        | Ước tính                                   |
|--------------------------------|--------------------------------------------|
| Số lượng văn bản ban đầu      | ~150.000 – 200.000 văn bản QPPL trung ương |
| Văn bản địa phương             | ~300.000 – 500.000 (63 tỉnh/thành)        |
| Tốc độ tăng trưởng            | ~5.000 – 10.000 văn bản mới/năm            |
| Người dùng đồng thời          | ~500 – 2.000 (cán bộ, luật sư, công dân)  |
| Truy vấn tìm kiếm/ngày       | ~10.000 – 50.000                            |

### 2.4. Ngoài phạm vi

- Soạn thảo văn bản mới (hệ thống chỉ tra cứu, không soạn thảo)
- Ký số / phê duyệt / quy trình ban hành văn bản
- OCR cho văn bản scan chất lượng thấp (hỗ trợ tùy chọn, không mặc định)
- Dịch sang ngôn ngữ khác

<div style="page-break-after: always;"></div>

## 3. Kiến trúc tổng thể

### 3.1. Sơ đồ kiến trúc phân lớp

Hệ thống được tổ chức thành **7 lớp** xếp chồng, mỗi lớp chỉ giao tiếp với lớp liền kề:

```
┌───────────────────────────────────────────────────────────────────┐
│                    Lớp Giao diện (Frontend)                       │
│      Web Portal │ Mobile App │ API công khai                      │
├───────────────────────────────────────────────────────────────────┤
│                       Lớp API Gateway                             │
│      REST API │ GraphQL │ Authentication │ Rate Limiting          │
├───────────────────────────────────────────────────────────────────┤
│                       Lớp AI (LLM + RAG)                          │
│   Embedding │ Q&A │ Tóm tắt │ Auto-tag │ Trích xuất quan hệ     │
├───────────────────────────────────────────────────────────────────┤
│              Lớp Tri thức — Knowledge Wiki (Obsidian)             │
│   Wiki biên dịch │ Trang chủ đề pháp lý │ Liên kết chéo │ Lint  │
├───────────────────────────────────────────────────────────────────┤
│                 Lớp Tìm kiếm & Truy xuất                         │
│    Elasticsearch (BM25) │ Vector DB │ Hybrid (RRF) │ Facet       │
├───────────────────────────────────────────────────────────────────┤
│                  Lớp Thu thập (Ingestion)                         │
│   Crawler │ Parser │ Chuẩn hóa │ Trích xuất cấu trúc pháp lý   │
├───────────────────────────────────────────────────────────────────┤
│                      Lớp Lưu trữ                                  │
│  PostgreSQL │ Elasticsearch │ Qdrant/pgvector │ Object Storage   │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2. Sơ đồ tương tác giữa các thành phần

```
                  ┌──────────────┐
                  │  Web Portal  │
                  │  Mobile App  │
                  └──────┬───────┘
                         │ HTTPS
                  ┌──────▼───────┐
                  │ API Gateway  │──── Auth / Rate Limit
                  └──┬───┬───┬──┘
                     │   │   │
         ┌───────────┘   │   └───────────┐
         │               │               │
  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
  │Search Service│ │  Q&A (RAG)  │ │ Wiki Service│
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │               │
         │        ┌──────▼──────┐        │
         │        │  LLM Service │        │
         │        └──────┬──────┘        │
         │               │               │
    ┌────▼───────────────▼───────────────▼────┐
    │           Elasticsearch                  │
    │    Full-text (BM25) + Wiki content       │
    ├──────────────────────────────────────────┤
    │        Vector DB (Qdrant / pgvector)     │
    ├──────────────────────────────────────────┤
    │           PostgreSQL (metadata)          │
    ├──────────────────────────────────────────┤
    │       Object Storage (file gốc)          │
    └──────────────────────────────────────────┘
              ▲
              │
    ┌─────────┴─────────┐
    │ Ingestion Pipeline │◄── Crawler / Upload / API
    └───────────────────┘
              ▲
              │
    ┌─────────┴─────────┐
    │  Obsidian Vault    │ ◄── Admin biên tập wiki
    │  (Git-synced)      │     qua Obsidian desktop
    └───────────────────┘
```

### 3.3. Nguyên tắc thiết kế

| Nguyên tắc                       | Giải thích                                                                 |
|----------------------------------|---------------------------------------------------------------------------|
| **Tách biệt thu thập và truy vấn** | Pipeline nhập liệu chạy độc lập, không ảnh hưởng hiệu năng tìm kiếm    |
| **Multi-source of truth**        | Văn bản gốc (PDF/HTML) là source of truth; metadata, index, wiki là derived |
| **Compile, don't search**        | Tri thức pháp lý được "biên dịch" thành wiki có cấu trúc, không chỉ tìm trên raw text (Karpathy LLM Wiki Pattern) |
| **Traceability**                 | Mọi kết quả AI ghi lại model + confidence — có thể xác minh và tái xử lý |
| **Hiệu lực pháp lý là trung tâm** | Mọi văn bản đều có trạng thái hiệu lực; tìm kiếm mặc định ưu tiên văn bản còn hiệu lực |
| **Obsidian-native wiki**         | Wiki được lưu dạng markdown trong Obsidian vault — admin đọc, sửa, review trực tiếp bằng Obsidian |
| **Horizontal scalable**          | Kiến trúc microservice, mỗi thành phần scale độc lập theo tải             |

<div style="page-break-after: always;"></div>

## 4. Mô tả các thành phần

### 4.1. Lớp Lưu trữ (Storage Layer)

Lớp nền tảng chịu trách nhiệm lưu trữ bền vững toàn bộ dữ liệu.

#### 4.1.1. PostgreSQL — Metadata & Quan hệ

- **Vai trò**: Lưu trữ metadata văn bản, quan hệ pháp lý (thay thế, sửa đổi, hướng dẫn), thông tin hiệu lực, lịch sử cập nhật
- **Lý do chọn**: Hỗ trợ quan hệ phức tạp giữa các văn bản, ACID transactions, JSON/JSONB cho metadata mở rộng, pgvector nếu cần vector search tích hợp
- **Schema**: Normalized với junction tables cho quan hệ nhiều-nhiều (xem mục [6. Mô hình dữ liệu](#6-mô-hình-dữ-liệu))

#### 4.1.2. Elasticsearch — Full-text Index

- **Vai trò**: Chỉ mục full-text search cho nội dung văn bản tiếng Việt, hỗ trợ BM25 ranking, highlighting, và aggregation cho faceted search
- **Lý do chọn**: Tokenizer hỗ trợ tiếng Việt (ICU + custom analyzer), scale ngang tốt, aggregation mạnh cho facet counts

#### 4.1.3. Vector Database (Qdrant hoặc pgvector)

- **Vai trò**: Lưu trữ embeddings cho tìm kiếm ngữ nghĩa
- **Hai phương án**:
  - **Qdrant** (standalone): Hiệu năng cao, hỗ trợ filtering trên metadata, HNSW index
  - **pgvector** (trong PostgreSQL): Đơn giản hơn, ít thành phần vận hành, phù hợp quy mô < 5M vectors

#### 4.1.4. Object Storage (MinIO / S3)

- **Vai trò**: Lưu file gốc (PDF, HTML snapshot) theo hash SHA-256, đảm bảo immutable và chống trùng lặp

```
storage/
├── originals/                    ← File gốc (PDF, HTML snapshot)
│   └── ab/cd/abcdef....pdf
├── extracted/                    ← Text trích xuất (markdown)
│   └── ab/cd/abcdef....md
└── structured/                   ← Cấu trúc pháp lý (JSON)
    └── ab/cd/abcdef....json
```

---

### 4.2. Lớp Thu thập (Ingestion Pipeline)

Chịu trách nhiệm nhập văn bản từ nhiều nguồn, trích xuất nội dung, chuẩn hóa cấu trúc pháp lý.

#### 4.2.1. Crawler Service

Thu thập văn bản từ các nguồn trực tuyến:

| Nguồn                | Tần suất    | Phương thức                          |
|----------------------|-------------|--------------------------------------|
| Công báo điện tử     | 2 lần/ngày  | RSS + Crawl page mới                |
| vbpl.vn              | 1 lần/ngày  | API + Crawl incremental             |
| Cổng Chính phủ       | 1 lần/ngày  | Crawl sitemap delta                  |
| UBND tỉnh/thành      | 1 lần/tuần  | Crawl + đối chiếu với batch trước   |

#### 4.2.2. Bộ phát hiện trùng lặp (Deduplicator)

- Tính SHA-256 hash nội dung → đối chiếu với database
- Phát hiện văn bản cùng số hiệu nhưng từ nguồn khác → merge metadata, giữ bản có chất lượng cao nhất

#### 4.2.3. Bộ trích xuất nội dung (Text Extraction)

| Định dạng | Công cụ                    | Đầu ra                    |
|-----------|----------------------------|---------------------------|
| PDF       | pymupdf4llm / marker-pdf   | Markdown + metadata       |
| HTML      | trafilatura + BeautifulSoup | Markdown + metadata       |
| DOC/DOCX  | python-docx / LibreOffice  | Markdown                  |
| XML       | lxml                       | Structured data + markdown |

#### 4.2.4. Bộ phân tích cấu trúc pháp lý (Legal Structure Parser)

Đây là thành phần **đặc thù nhất** của hệ thống, chịu trách nhiệm phân tích cấu trúc phân cấp của văn bản pháp luật Việt Nam:

**Cấu trúc điển hình của một đạo Luật:**

```
Luật Đất đai 2024 (Luật số 31/2024/QH15)
├── Phần thứ nhất: QUY ĐỊNH CHUNG
│   ├── Chương I: NHỮNG QUY ĐỊNH CHUNG
│   │   ├── Điều 1: Phạm vi điều chỉnh
│   │   ├── Điều 2: Đối tượng áp dụng
│   │   │   ├── Khoản 1: ...
│   │   │   │   ├── Điểm a: ...
│   │   │   │   └── Điểm b: ...
│   │   │   └── Khoản 2: ...
│   │   └── Điều 3: Giải thích từ ngữ
│   └── Chương II: ...
└── Phần thứ hai: ...
```

**Phân cấp**: Phần → Chương → Mục → Tiểu mục → Điều → Khoản → Điểm

Parser sử dụng **regex patterns + heuristics** (cho phần lớn văn bản có cấu trúc rõ ràng) kết hợp **LLM fallback** (cho văn bản cấu trúc bất thường):

```
Văn bản thô
  │
  ├─→ Regex pattern matching (Phần/Chương/Mục/Điều/Khoản/Điểm)
  ├─→ Trích xuất metadata từ header (số hiệu, ngày ban hành, cơ quan)
  ├─→ Xác định quan hệ pháp lý (thay thế, sửa đổi, hướng dẫn)
  └─→ Sinh JSON cấu trúc phân cấp + ánh xạ vị trí text
```

#### 4.2.5. Bộ trích xuất quan hệ pháp lý (Legal Relation Extractor)

Phát hiện và lưu trữ quan hệ giữa các văn bản:

| Quan hệ             | Ví dụ                                                      |
|----------------------|-------------------------------------------------------------|
| **Thay thế**         | Luật Đất đai 2024 thay thế Luật Đất đai 2013               |
| **Sửa đổi bổ sung**  | Luật sửa đổi Điều 3 Luật X                                 |
| **Hướng dẫn thi hành** | Nghị định 43/2014/NĐ-CP hướng dẫn Luật Đất đai 2013     |
| **Bãi bỏ**          | Nghị định Y bãi bỏ Điều 5 Nghị định Z                      |
| **Viện dẫn**         | Điều 10 Luật A viện dẫn Điều 20 Luật B                     |

Phương pháp: kết hợp **regex** (cho các mẫu câu phổ biến: "thay thế", "sửa đổi", "hướng dẫn thi hành", "căn cứ") + **LLM** (cho các trường hợp viện dẫn phức tạp hoặc ngầm).

#### 4.2.6. Bộ lập chỉ mục (Indexer)

Sau khi trích xuất, thực hiện song song:
- Cập nhật chỉ mục Elasticsearch (full-text)
- Tạo embeddings và lưu vào Vector DB
- Cập nhật metadata trong PostgreSQL
- Đặt job biên dịch wiki vào hàng đợi

---

### 4.3. Lớp Tìm kiếm & Truy xuất (Search & Retrieval Layer)

Cung cấp khả năng tìm kiếm đa phương thức, kết hợp từ khóa và ngữ nghĩa.

*(Chi tiết thuật toán tại mục [7. Chiến lược tìm kiếm](#7-chiến-lược-tìm-kiếm))*

| Thành phần              | Vai trò                                                       |
|-------------------------|---------------------------------------------------------------|
| Elasticsearch (BM25)    | Tìm kiếm theo từ khóa/thuật ngữ pháp lý, xếp hạng BM25      |
| Vector Search           | Tìm kiếm theo ngữ nghĩa, dùng cosine similarity              |
| RRF Fusion              | Kết hợp kết quả BM25 + Vector bằng Reciprocal Rank Fusion     |
| Faceted Filter          | Lọc theo loại văn bản, cơ quan ban hành, năm, lĩnh vực, hiệu lực |
| Re-ranker               | Xếp hạng lại top kết quả bằng cross-encoder (tùy chọn)        |
| Legal Hierarchy Search  | Tìm kiếm đến cấp Điều/Khoản/Điểm, trả về vị trí chính xác   |

---

### 4.4. Lớp AI (LLM + RAG)

Tích hợp các mô hình AI để tự động hóa việc khai thác kho văn bản pháp luật.

*(Chi tiết tại mục [8. Tích hợp AI](#8-tích-hợp-ai))*

| Thành phần              | Vai trò                                                           |
|-------------------------|-------------------------------------------------------------------|
| Embedding Service       | Sinh vector embeddings cho văn bản tiếng Việt (chunk-level + doc-level) |
| Q&A Engine (RAG)        | Hỏi đáp pháp luật với trích dẫn đến Điều/Khoản cụ thể            |
| Auto-Summarizer         | Tóm tắt văn bản dài (đặc biệt Luật, Nghị định nhiều chương)      |
| Auto-Tagger             | Gán nhãn lĩnh vực pháp lý (đất đai, thuế, lao động, ...)         |
| Relation Extractor (AI) | Phát hiện quan hệ pháp lý ngầm khi regex không đủ                 |
| Wiki Compiler           | Biên dịch văn bản mới thành trang wiki pháp lý                    |
| Job Queue               | Xử lý các tác vụ AI ở background, không chặn pipeline chính       |

---

### 4.5. Lớp Tri thức — Knowledge Wiki (Obsidian)

*(Chi tiết tại mục [9. Knowledge Wiki (Obsidian)](#9-knowledge-wiki-obsidian))*

Lớp này áp dụng **Karpathy LLM Wiki Pattern** cho miền pháp luật: thay vì chỉ tìm kiếm trên raw text mỗi khi truy vấn, hệ thống **biên dịch tri thức pháp lý** thành wiki có cấu trúc, do LLM tạo và admin review/chỉnh sửa qua **Obsidian**.

**Vai trò của Obsidian**: Obsidian đóng vai trò **"IDE cho pháp chế"** — admin/chuyên viên pháp lý mở Obsidian vault, đọc các trang wiki do LLM tạo, chỉnh sửa, thêm ghi chú, tạo liên kết — tất cả được sync về hệ thống qua Git.

---

### 4.6. Lớp API Gateway

Điểm vào duy nhất cho tất cả client (web, mobile, bên thứ ba).

| Chức năng           | Mô tả                                                         |
|---------------------|---------------------------------------------------------------|
| Authentication      | JWT token + OAuth2 cho người dùng nội bộ, API key cho bên thứ ba |
| Rate Limiting       | Giới hạn truy vấn theo tier (công dân miễn phí, cơ quan ưu tiên) |
| Request Routing     | Chuyển request đến đúng service (search, Q&A, wiki)            |
| Response Caching    | Cache kết quả tìm kiếm phổ biến (TTL ngắn vì dữ liệu thay đổi) |
| API Versioning      | Hỗ trợ nhiều phiên bản API cùng lúc                            |

---

### 4.7. Lớp Giao diện (Frontend)

| Giao diện           | Đối tượng              | Chức năng chính                                   |
|---------------------|------------------------|--------------------------------------------------|
| Web Portal          | Công dân, luật sư       | Tìm kiếm, xem văn bản, hỏi đáp pháp luật        |
| Admin Panel         | Cán bộ quản trị         | Quản lý nguồn, theo dõi ingestion, thống kê       |
| Obsidian Vault      | Chuyên viên pháp chế    | Biên tập wiki pháp lý, review nội dung AI tạo    |
| Mobile App          | Công dân (tương lai)    | Tra cứu nhanh trên điện thoại                     |
| API công khai       | Hệ thống bên thứ ba     | Tích hợp tra cứu pháp luật vào ứng dụng khác     |

<div style="page-break-after: always;"></div>

## 5. Luồng dữ liệu chính

### 5.1. Luồng Thu thập văn bản (Ingestion Flow)

```
               Nguồn văn bản
        (Công báo, vbpl.vn, UBND, ...)
                    │
        ┌───────────▼───────────┐
        │   Crawler / Upload     │
        └───────────┬───────────┘
                    │
       ┌────────────▼────────────┐
       │  1. Phát hiện trùng lặp  │
       │     SHA-256 + số hiệu   │
       └─────┬────────────┬──────┘
        Đã có│            │ Mới
     ┌───────▼──┐  ┌──────▼──────────┐
     │ Merge    │  │ 2. Lưu file gốc │
     │ metadata │  │    (Object Store)│
     └──────────┘  └──────┬──────────┘
                          │
          ┌───────────────▼───────────────┐
          │  3. Trích xuất nội dung       │
          │     PDF/HTML/DOC → Markdown   │
          └───────────────┬───────────────┘
                          │
          ┌───────────────▼───────────────┐
          │  4. Phân tích cấu trúc        │
          │     Phần/Chương/Điều/Khoản    │
          │     → JSON cấu trúc phân cấp  │
          └───────────────┬───────────────┘
                          │
          ┌───────────────▼───────────────┐
          │  5. Trích xuất quan hệ         │
          │     Thay thế, sửa đổi,         │
          │     hướng dẫn, viện dẫn        │
          └───────────────┬───────────────┘
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
┌─────▼──────┐   ┌───────▼───────┐   ┌──────▼──────┐
│ 6a. Elastic│   │ 6b. Embedding │   │ 6c. Postgres│
│ search     │   │ → Vector DB   │   │ metadata    │
│ indexing   │   │               │   │ + quan hệ   │
└─────┬──────┘   └───────┬───────┘   └──────┬──────┘
      │                   │                   │
      └───────────────────┼───────────────────┘
                          │
          ┌───────────────▼───────────────┐
          │  7. Wiki Compilation          │
          │     LLM tạo/cập nhật trang    │
          │     wiki pháp lý              │
          └───────────────────────────────┘
```

### 5.2. Luồng Tìm kiếm (Search Flow)

```
                     Truy vấn người dùng
               "Quy định về chuyển nhượng đất đai"
                            │
                ┌───────────▼───────────┐
                │  Tiền xử lý truy vấn  │
                │  (tokenize tiếng Việt, │
                │   synonym expansion)   │
                └───────┬───────┬───────┘
                        │       │
                ┌───────▼──┐ ┌──▼───────┐
                │ BM25     │ │ Vector   │
                │ (Elastic)│ │ Search   │
                │ Top 200  │ │ Top 200  │
                └───────┬──┘ └──┬───────┘
                        │       │
                ┌───────▼───────▼───────┐
                │      RRF Fusion       │
                │      Top 50 kết hợp   │
                └───────────┬───────────┘
                            │
                ┌───────────▼───────────┐
                │   Lọc Facet           │
                │   Loại VB, năm,       │
                │   cơ quan, hiệu lực   │
                └───────────┬───────────┘
                            │
                ┌───────────▼───────────┐
                │   Ưu tiên hiệu lực   │
                │   Còn hiệu lực ↑     │
                │   Hết hiệu lực ↓     │
                └───────────┬───────────┘
                            │
                ┌───────────▼───────────┐
                │   Re-rank (tùy chọn)  │
                │   Cross-encoder       │
                └───────────┬───────────┘
                            │
                ┌───────────▼───────────┐
                │   Kết quả + Facet     │
                │   counts + Highlights │
                └───────────────────────┘
```

### 5.3. Luồng Hỏi đáp pháp luật (Q&A / RAG Flow)

```
          Câu hỏi người dùng
  "Điều kiện chuyển nhượng quyền sử dụng đất
   đối với hộ gia đình theo Luật Đất đai 2024?"
                    │
        ┌───────────┼───────────┐
        │                       │
┌───────▼───────┐     ┌────────▼────────┐
│ Hybrid Search │     │ Wiki Search     │
│ (BM25+Vector) │     │ (trang pháp lý  │
│ → raw chunks  │     │  đã biên dịch)  │
│ (Điều/Khoản)  │     │                 │
└───────┬───────┘     └────────┬────────┘
        │                       │
        └───────────┬───────────┘
                    │
         ┌──────────▼──────────┐
         │  Cross-Encoder      │
         │  Re-rank → Top 5   │
         └──────────┬──────────┘
                    │
         ┌──────────▼──────────┐
         │  LLM sinh câu trả  │
         │  lời + trích dẫn   │
         │  (Điều, Khoản, VB) │
         └──────────┬──────────┘
                    │
                    ▼
             Câu trả lời
    + [(Luật Đất đai 2024, Điều 45, Khoản 2),
       (NĐ 43/2014, Điều 12, Khoản 1), ...]
```

### 5.4. Luồng Biên dịch Wiki (Wiki Compilation Flow)

```
        Văn bản mới được nhập
        (VD: Nghị định mới hướng dẫn Luật Đất đai)
                    │
         ┌──────────▼──────────┐
         │  LLM đọc & phân    │
         │  tích nội dung      │
         └──────────┬──────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
┌───▼────┐   ┌─────▼─────┐   ┌────▼──────┐
│ Tạo    │   │ Cập nhật  │   │ Thêm     │
│ trang  │   │ trang chủ │   │ liên kết │
│ tóm tắt│   │ đề liên   │   │ chéo     │
│ VB mới │   │ quan      │   │ (backlink│
└───┬────┘   └─────┬─────┘   └────┬──────┘
    │               │               │
    └───────────────┼───────────────┘
                    │
         ┌──────────▼──────────┐
         │  Commit vào         │
         │  Obsidian vault     │
         │  (Git)              │
         └──────────┬──────────┘
                    │
         ┌──────────▼──────────┐
         │  Admin review       │
         │  trong Obsidian     │
         │  (tùy chọn)        │
         └─────────────────────┘
```

<div style="page-break-after: always;"></div>

## 6. Mô hình dữ liệu

### 6.1. Triết lý thiết kế

Mô hình dữ liệu phản ánh **cấu trúc đặc thù của văn bản pháp luật Việt Nam**:

- Mỗi văn bản có **cấu trúc phân cấp** (Phần → Chương → Mục → Điều → Khoản → Điểm)
- Văn bản có **trạng thái hiệu lực** thay đổi theo thời gian
- Văn bản có **quan hệ phức tạp** với nhau (thay thế, sửa đổi, hướng dẫn, viện dẫn)
- Cùng một điều khoản có thể bị **sửa đổi một phần** bởi văn bản khác

### 6.2. Sơ đồ thực thể - quan hệ (ER Overview)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐  │
│  │ issuing_bodies│◄────┤ doc_issuing_body ├────►│   documents    │  │
│  └──────────────┘     └──────────────────┘     └───────┬────────┘  │
│                                                         │           │
│  ┌──────────────┐     ┌──────────────────┐              │           │
│  │  legal_fields│◄────┤ doc_legal_fields ├──────────────┤           │
│  └──────────────┘     └──────────────────┘              │           │
│                                                         │           │
│  ┌──────────────┐                                       │           │
│  │  doc_sections│◄──────────────────────────────────────┤           │
│  │  (phân cấp   │    (Phần/Chương/Mục/Điều/Khoản/Điểm)│           │
│  │   pháp lý)   │                                       │           │
│  └──────────────┘                                       │           │
│                                                         │           │
│  ┌──────────────────┐                                   │           │
│  │ doc_relations    │◄──────────────────────────────────┤           │
│  │ (thay thế, sửa   │  (self-referencing qua            │           │
│  │  đổi, hướng dẫn) │   source_doc_id + target_doc_id) │           │
│  └──────────────────┘                                   │           │
│                                                         │           │
│  ┌──────────────────┐                                   │           │
│  │ doc_effectiveness│◄──────────────────────────────────┤           │
│  │ (lịch sử hiệu   │                                   │           │
│  │  lực theo thời   │                                   │           │
│  │  gian)           │                                   │           │
│  └──────────────────┘                                   │           │
│                                                         │           │
│  ┌──────────────┐                                       │           │
│  │   chunks     │◄──────────────────────────────────────┘           │
│  │ (đoạn text   │                                                   │
│  │  cho RAG)    │                                                   │
│  └──────────────┘                                                   │
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐                          │
│  │ wiki_pages   │◄────┤wiki_page_sources ├─────────────┐            │
│  └──────┬───────┘     └──────────────────┘             │            │
│         │                                          (documents)      │
│  ┌──────▼───────┐                                                   │
│  │ wiki_links   │  (liên kết chéo giữa wiki pages)                 │
│  └──────────────┘                                                   │
│  ┌──────────────┐                                                   │
│  │ wiki_log     │  (nhật ký ingest/query/lint)                     │
│  └──────────────┘                                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3. Mô tả các bảng chính

#### Bảng `documents` — Văn bản

| Cột                     | Kiểu      | Mô tả                                                    |
|-------------------------|-----------|-----------------------------------------------------------|
| id                      | SERIAL    | Khóa chính                                                 |
| doc_number              | TEXT      | Số hiệu văn bản (VD: "31/2024/QH15")                      |
| title                   | TEXT      | Tên văn bản                                                 |
| doc_type                | TEXT      | Loại: luat, phap_lenh, nghi_dinh, thong_tu, quyet_dinh, ... |
| issuing_date            | DATE      | Ngày ban hành                                               |
| effective_date          | DATE      | Ngày có hiệu lực                                           |
| expiry_date             | DATE      | Ngày hết hiệu lực (NULL = không xác định)                  |
| effectiveness_status    | TEXT      | con_hieu_luc, het_hieu_luc, chua_co_hieu_luc, het_hieu_luc_mot_phan |
| gazette_number          | TEXT      | Số Công báo                                                 |
| signer                  | TEXT      | Người ký                                                     |
| file_hash               | TEXT      | SHA-256 hash file gốc                                       |
| content_markdown        | TEXT      | Nội dung đã trích xuất (markdown)                           |
| structure_json          | JSONB     | Cấu trúc phân cấp (Phần/Chương/Điều/Khoản/Điểm)           |
| summary                 | TEXT      | Tóm tắt do AI tạo                                           |
| summary_model           | TEXT      | Model nào tạo tóm tắt                                       |
| source_url              | TEXT      | URL nguồn gốc                                               |
| created_at              | TIMESTAMP | Thời điểm nhập vào hệ thống                                 |
| updated_at              | TIMESTAMP | Thời điểm cập nhật gần nhất                                 |

#### Bảng `doc_sections` — Phân cấp pháp lý

| Cột              | Kiểu      | Mô tả                                                |
|------------------|-----------|-------------------------------------------------------|
| id               | SERIAL    | Khóa chính                                             |
| document_id      | INTEGER   | FK → documents                                        |
| parent_id        | INTEGER   | FK → doc_sections (self-referencing, cây phân cấp)    |
| section_type     | TEXT      | phan, chuong, muc, tieu_muc, dieu, khoan, diem        |
| number           | TEXT      | Số thứ tự ("1", "2", "a", "b")                        |
| title            | TEXT      | Tiêu đề (nếu có, VD: "Phạm vi điều chỉnh")          |
| content          | TEXT      | Nội dung text của mục này                              |
| position_start   | INTEGER   | Vị trí bắt đầu trong content_markdown                 |
| position_end     | INTEGER   | Vị trí kết thúc trong content_markdown                 |

#### Bảng `doc_relations` — Quan hệ pháp lý

| Cột              | Kiểu      | Mô tả                                                |
|------------------|-----------|-------------------------------------------------------|
| id               | SERIAL    | Khóa chính                                             |
| source_doc_id    | INTEGER   | FK → documents (văn bản nguồn)                        |
| target_doc_id    | INTEGER   | FK → documents (văn bản đích)                          |
| relation_type    | TEXT      | thay_the, sua_doi, huong_dan, bai_bo, vien_dan         |
| source_section   | TEXT      | Điều/Khoản cụ thể trong văn bản nguồn (tùy chọn)     |
| target_section   | TEXT      | Điều/Khoản cụ thể trong văn bản đích (tùy chọn)       |
| detected_by      | TEXT      | regex / llm / manual                                   |
| confidence       | FLOAT     | Độ tin cậy (1.0 cho regex/manual, 0.0–1.0 cho LLM)    |

#### Bảng `chunks` — Đoạn text cho RAG

| Cột              | Kiểu      | Mô tả                                                |
|------------------|-----------|-------------------------------------------------------|
| id               | SERIAL    | Khóa chính                                             |
| document_id      | INTEGER   | FK → documents                                        |
| section_id       | INTEGER   | FK → doc_sections (chunk thuộc Điều/Khoản nào)        |
| content          | TEXT      | Nội dung chunk                                         |
| chunk_index      | INTEGER   | Thứ tự chunk trong văn bản                             |
| embedding_id     | TEXT      | ID trong Vector DB                                     |

#### Bảng `wiki_pages` — Trang wiki pháp lý

| Cột              | Kiểu      | Mô tả                                                |
|------------------|-----------|-------------------------------------------------------|
| id               | SERIAL    | Khóa chính                                             |
| slug             | TEXT      | Đường dẫn trong Obsidian vault                         |
| title            | TEXT      | Tiêu đề trang                                          |
| page_type        | TEXT      | linh_vuc, chu_de, tom_tat_vb, khai_niem, timeline      |
| content          | TEXT      | Nội dung markdown                                       |
| frontmatter      | JSONB     | YAML frontmatter (sources, tags, ...)                   |
| created_by_model | TEXT      | Model LLM nào tạo                                      |
| reviewed         | BOOLEAN   | Admin đã review chưa                                    |
| created_at       | TIMESTAMP | Ngày tạo                                                |
| updated_at       | TIMESTAMP | Ngày cập nhật gần nhất                                  |

### 6.4. Chiến lược đánh index

| Index                          | Mục đích                                     |
|--------------------------------|----------------------------------------------|
| `idx_docs_number`              | Tra cứu nhanh theo số hiệu văn bản           |
| `idx_docs_type`                | Lọc theo loại văn bản                         |
| `idx_docs_effectiveness`       | Lọc theo trạng thái hiệu lực                 |
| `idx_docs_effective_date`      | Sắp xếp/lọc theo ngày hiệu lực              |
| `idx_docs_hash`                | Tra cứu trùng lặp nhanh (SHA-256)            |
| `idx_sections_doc_type`        | Tra cứu section theo document + loại section  |
| `idx_relations_source_target`  | Tra cứu quan hệ theo cặp văn bản             |
| `idx_chunks_doc`               | Tra cứu chunks theo document                  |
| `idx_wiki_slug`                | Tra cứu wiki page theo đường dẫn             |

<div style="page-break-after: always;"></div>

## 7. Chiến lược tìm kiếm

### 7.1. Tổng quan

Hệ thống kết hợp **3 phương thức** tìm kiếm, với các điều chỉnh đặc thù cho văn bản pháp luật tiếng Việt:

| Phương thức        | Ưu điểm                              | Hạn chế                              |
|--------------------|---------------------------------------|---------------------------------------|
| BM25 (từ khóa)     | Chính xác cho số hiệu VB, thuật ngữ pháp lý | Không hiểu đồng nghĩa/ngữ cảnh      |
| Vector (ngữ nghĩa) | Hiểu ý nghĩa, tìm quy định liên quan  | Yếu với số hiệu, tên riêng            |
| Hybrid (kết hợp)   | Tận dụng cả hai                        | Cần cân chỉnh trọng số                |

### 7.2. BM25 — Full-text Search trên Elasticsearch

**Xử lý tiếng Việt:**

Elasticsearch cần cấu hình custom analyzer cho tiếng Việt:

| Thành phần         | Cấu hình                                                         |
|--------------------|-------------------------------------------------------------------|
| Tokenizer          | ICU tokenizer (hỗ trợ Unicode tiếng Việt tốt)                    |
| Token filter       | ICU folding (bỏ dấu để tìm kiếm không dấu), lowercase            |
| Synonym filter     | Từ đồng nghĩa pháp lý ("QSDĐ" ↔ "quyền sử dụng đất", "NĐ" ↔ "Nghị định") |
| Stop words          | Loại bỏ từ dừng tiếng Việt ("của", "và", "hoặc", "theo", ...)   |

**Điều chỉnh BM25 cho văn bản pháp luật:**

| Tham số | Mặc định | Giá trị chọn | Lý do                                                             |
|---------|----------|---------------|-------------------------------------------------------------------|
| k₁      | 1.2      | **1.5**       | Văn bản pháp luật dài, thuật ngữ chuyên ngành xuất hiện nhiều lần hợp lệ |
| b        | 0.75     | **0.3**       | Luật 200 điều vs Công văn 2 trang — khác biệt nội dung thật, không nên phạt mạnh |

**Multi-field search:**

Tìm kiếm trên nhiều trường với trọng số khác nhau:

```
title^3.0           ← Tiêu đề văn bản (ưu tiên cao nhất)
doc_number^2.5      ← Số hiệu ("43/2014/NĐ-CP")
content^1.0         ← Nội dung toàn văn
section_titles^2.0  ← Tiêu đề các Điều
summary^1.5         ← Tóm tắt AI
```

### 7.3. Vector Search — Tìm kiếm ngữ nghĩa

**Embedding model cho tiếng Việt:**

| Model                              | Chiều | Đặc điểm                                              |
|------------------------------------|-------|--------------------------------------------------------|
| **bkai-foundation-models/vietnamese-bi-encoder** | 768   | Được huấn luyện trên dữ liệu tiếng Việt, hiệu năng tốt nhất cho tiếng Việt |
| multilingual-e5-large              | 1024  | Đa ngôn ngữ, hiệu năng tốt cho tiếng Việt, nặng hơn   |
| all-MiniLM-L6-v2                   | 384   | Nhẹ, nhanh, nhưng chủ yếu tối ưu cho tiếng Anh        |

**Khuyến nghị**: Sử dụng **vietnamese-bi-encoder** hoặc **multilingual-e5-large** vì tiếng Việt là ngôn ngữ chính. Đánh giá trên tập dữ liệu pháp lý thực tế trước khi chọn.

**Chiến lược chunking cho văn bản pháp lý:**

Thay vì chia theo số token cố định, chia theo **đơn vị pháp lý tự nhiên**:

| Cấp chunking       | Khi nào sử dụng                                           |
|---------------------|-----------------------------------------------------------|
| 1 chunk = 1 Điều   | Phổ biến nhất — mỗi Điều là một đơn vị ngữ nghĩa hoàn chỉnh |
| 1 chunk = 1 Khoản  | Khi Điều quá dài (> 512 tokens)                            |
| 1 chunk = 1 Chương | Cho document-level embedding                                |

Ưu điểm: Khi trả kết quả, có thể trích dẫn chính xác "Điều X, Khoản Y" thay vì "chunk thứ 47".

**Hiệu năng:**

| Số văn bản  | Số chunks ước tính | Brute-force  | HNSW      | Khuyến nghị     |
|-------------|-------------------|-------------|-----------|-----------------|
| 200.000     | ~2.000.000        | ~400ms      | ~2ms      | HNSW bắt buộc  |
| 500.000     | ~5.000.000        | ~1s         | ~3ms      | HNSW bắt buộc  |

→ Ở quy mô này, **HNSW index là bắt buộc** (khác với Liberito ở quy mô nhỏ hơn dùng brute-force).

### 7.4. Hybrid Search — Kết hợp bằng RRF

Sử dụng **Reciprocal Rank Fusion (RRF)** để kết hợp kết quả từ BM25 và Vector Search.

**Công thức:**

```
RRF_score(d) = Σ  wᵣ / (k + rankᵣ(d))
```

Trong đó:
- `k = 60` — hằng số (Cormack et al., 2009)
- `rankᵣ(d)` — thứ hạng của văn bản d trong ranker r
- `wᵣ` — trọng số của ranker r

**Trọng số mặc định:**

| Ngữ cảnh tìm kiếm         | w(BM25) | w(Vector) | Lý do                                                |
|----------------------------|---------|-----------|------------------------------------------------------|
| Tra cứu theo số hiệu/tiêu đề | 0.8     | 0.2       | Người dùng tìm chính xác theo thuật ngữ pháp lý     |
| Tìm quy định liên quan     | 0.4     | 0.6       | Ưu tiên ngữ nghĩa khi hỏi về chủ đề                |
| Q&A pháp luật              | 0.5     | 0.5       | Cân bằng                                              |

### 7.5. Faceted Search

Lọc nhanh theo các thuộc tính đặc thù của văn bản pháp luật:

| Facet                 | Giá trị ví dụ                                           |
|-----------------------|---------------------------------------------------------|
| Loại văn bản          | Luật, Nghị định, Thông tư, Quyết định, ...              |
| Cơ quan ban hành      | Quốc hội, Chính phủ, Bộ Tài chính, UBND TP.HCM, ...    |
| Lĩnh vực              | Đất đai, Thuế, Lao động, Hình sự, Dân sự, ...          |
| Năm ban hành          | 2020, 2021, 2022, 2023, 2024, ...                        |
| Trạng thái hiệu lực  | Còn hiệu lực, Hết hiệu lực, Hết hiệu lực một phần      |

Sử dụng **Elasticsearch aggregations** cho facet counts — tối ưu sẵn, không cần bitmap index tự xây.

### 7.6. Ưu tiên hiệu lực (Effectiveness Boosting)

Đặc thù của tìm kiếm pháp luật: người dùng hầu hết cần văn bản **còn hiệu lực**. Hệ thống áp dụng boosting mặc định:

```
Còn hiệu lực:           boost × 2.0 (mặc định)
Chưa có hiệu lực:       boost × 1.5
Hết hiệu lực một phần:  boost × 1.0
Hết hiệu lực:           boost × 0.3
```

Người dùng có thể tắt boosting khi cần nghiên cứu lịch sử pháp luật.

### 7.7. Pipeline tìm kiếm đầy đủ

| Bước | Thao tác                                 | Thời gian      |
|------|------------------------------------------|----------------|
| 1    | Tiền xử lý truy vấn (tokenize, synonym) | ~2ms           |
| 2a   | BM25 trên Elasticsearch → Top 200        | 10–30ms        |
| 2b   | Vector search (HNSW) → Top 200           | 2–5ms          |
| 3    | RRF Fusion → Top 50                      | ~0.1ms         |
| 4    | Facet filter + aggregation                | 5–15ms         |
| 5    | Effectiveness boosting                    | ~0.1ms         |
| 6    | Re-rank (tùy chọn, top 20–50)            | 200–500ms      |
| **Tổng** | **Không re-rank**                    | **~20–55ms**   |
| **Tổng** | **Có re-rank**                       | **~220–555ms** |

<div style="page-break-after: always;"></div>

## 8. Tích hợp AI

### 8.1. Kiến trúc LLM Service

Hệ thống sử dụng **LLM service tập trung** phục vụ tất cả các tác vụ AI, với khả năng chuyển đổi giữa các provider:

| Provider    | Model                  | Dùng cho                               |
|-------------|------------------------|----------------------------------------|
| OpenAI      | gpt-4o-mini / gpt-4o   | Tóm tắt, gán tag, trích xuất quan hệ  |
| Anthropic   | claude-haiku / sonnet   | Q&A, biên dịch wiki (chất lượng cao)  |
| Ollama      | Vistral / Qwen2.5       | Chạy nội bộ khi cần bảo mật dữ liệu  |

### 8.2. Embedding Service

| Thành phần     | Cấu hình                                                           |
|----------------|---------------------------------------------------------------------|
| Model          | vietnamese-bi-encoder (768-dim) hoặc multilingual-e5-large (1024-dim) |
| Batch size     | 128 chunks/batch                                                     |
| Chunking       | Theo đơn vị pháp lý (Điều/Khoản), fallback fixed-size 512 tokens    |
| Indexing       | HNSW (Qdrant) hoặc IVFFlat (pgvector)                               |

### 8.3. Q&A Engine (RAG Pipeline)

Pipeline RAG cho hỏi đáp pháp luật:

```
Câu hỏi → ┬─ Hybrid search → raw chunks (Điều/Khoản)
           └─ Wiki search → trang wiki pháp lý đã biên dịch
        → Cross-encoder re-rank → Top 5 (wiki + raw)
        → LLM sinh câu trả lời kèm trích dẫn pháp lý
        → Trả về: câu trả lời + [(tên_VB, Điều, Khoản, trích_đoạn), ...]
```

**Yêu cầu quan trọng cho Q&A pháp luật:**
- Mọi khẳng định phải có **trích dẫn** đến Điều/Khoản/Điểm cụ thể
- Nếu không tìm thấy căn cứ → phải nói rõ "không tìm thấy quy định liên quan", không được bịa
- Phân biệt rõ giữa quy định **còn hiệu lực** và **đã hết hiệu lực**
- Nếu có sửa đổi bổ sung → trích dẫn phiên bản mới nhất và ghi chú phiên bản cũ

### 8.4. Auto-Summarization

Tóm tắt văn bản pháp luật theo hai bậc:

| Bậc | Khi nào                  | Input                          | Output                              |
|-----|--------------------------|--------------------------------|--------------------------------------|
| 1   | Ngay khi nhập            | 3000 tokens đầu               | 2–3 câu tóm tắt nội dung chính     |
| 2   | Background / on-demand   | Toàn bộ văn bản (chunk-wise)  | Tóm tắt theo cấu trúc Chương/Điều   |

### 8.5. Auto-Tagging — Gán nhãn lĩnh vực pháp lý

```
Input:  Trích đoạn văn bản + danh sách lĩnh vực hiện có
Output: {fields: ["đất đai", "xây dựng"], confidence: 0.92}

Quy tắc:
  ─ confidence ≥ 0.85 → tự động áp dụng
  ─ confidence < 0.85 → hàng đợi chờ admin duyệt
  ─ Ghi nhận source='auto' + tên model
```

Danh mục lĩnh vực tuân theo **phân loại của Bộ Tư pháp** (đất đai, thuế, lao động, dân sự, hình sự, hành chính, thương mại, môi trường, ...).

### 8.6. Trích xuất quan hệ pháp lý bằng AI

Bổ sung cho regex parser — xử lý các trường hợp phức tạp:

| Trường hợp                    | Ví dụ                                                              |
|-------------------------------|---------------------------------------------------------------------|
| Viện dẫn ngầm                 | "theo quy định của pháp luật về đất đai" (không nêu số hiệu)       |
| Thay thế một phần             | "sửa đổi Khoản 2 Điều 5" (cần xác định đúng Điều/Khoản)           |
| Liên kết chủ đề               | Nghị định A và Nghị định B cùng hướng dẫn một Luật nhưng khác chương |

### 8.7. Traceability

Mọi kết quả AI đều được ghi lại:
- **Model nào** tạo ra (tên + phiên bản)
- **Confidence** của kết quả
- **Nguồn** (auto / manual / admin-reviewed)

Cho phép:
- Tái xử lý khi đổi model tốt hơn
- Phân biệt metadata do AI vs do admin tạo
- Admin review dần dần kết quả AI

<div style="page-break-after: always;"></div>

## 9. Knowledge Wiki (Obsidian)

### 9.1. Ý tưởng cốt lõi

Áp dụng **Karpathy LLM Wiki Pattern** cho miền pháp luật hành chính:

> *"Obsidian is the IDE, the LLM is the programmer, the wiki is the codebase."* — Andrej Karpathy

**Phép ẩn dụ trình biên dịch:**

| Lập trình            | Hệ thống văn bản hành chính                              |
|----------------------|-----------------------------------------------------------|
| Mã nguồn (source)   | Văn bản gốc (Luật, Nghị định, Thông tư) — immutable      |
| Biên dịch (compile)  | LLM đọc văn bản → sinh trang wiki pháp lý có cấu trúc   |
| Mã máy (binary)     | Knowledge Wiki — markdown đã tinh chế                     |
| IDE                  | Obsidian — nơi admin đọc, review, chỉnh sửa wiki         |
| Chạy (runtime)       | Truy vấn trên wiki thay vì raw text                      |

### 9.2. Cấu trúc Obsidian Vault

```
wiki-phap-luat/                          ← Obsidian vault (Git-synced)
├── .obsidian/                           ← Cấu hình Obsidian
│   ├── workspace.json
│   └── plugins/                         ← Plugins hỗ trợ
├── index.md                             ← Mục lục tự động, LLM duy trì
├── log.md                               ← Nhật ký append-only
├── linh-vuc/                            ← Trang theo lĩnh vực pháp lý
│   ├── dat-dai.md                       ← Tổng quan pháp luật đất đai
│   ├── thue.md                          ← Tổng quan pháp luật thuế
│   ├── lao-dong.md
│   └── ...
├── chu-de/                              ← Trang theo chủ đề cụ thể
│   ├── chuyen-nhuong-quyen-su-dung-dat.md
│   ├── thue-thu-nhap-ca-nhan.md
│   ├── hop-dong-lao-dong.md
│   └── ...
├── tom-tat/                             ← Tóm tắt từng văn bản
│   ├── luat-dat-dai-2024.md
│   ├── nd-43-2014-nd-cp.md
│   └── ...
├── khai-niem/                           ← Giải thích thuật ngữ pháp lý
│   ├── quyen-su-dung-dat.md
│   ├── so-huu-toan-dan.md
│   └── ...
├── timeline/                            ← Dòng thời gian thay đổi pháp luật
│   ├── lich-su-phap-luat-dat-dai.md
│   └── ...
└── templates/                           ← Template cho các loại trang
    ├── linh-vuc-template.md
    ├── chu-de-template.md
    └── tom-tat-template.md
```

### 9.3. Frontmatter chuẩn

Mỗi trang wiki có **YAML frontmatter** để Obsidian và hệ thống cùng hiểu:

```yaml
---
title: "Chuyển nhượng quyền sử dụng đất"
type: chu_de                    # linh_vuc | chu_de | tom_tat | khai_niem | timeline
sources:                        # Văn bản gốc
  - doc_id: 1234
    doc_number: "31/2024/QH15"
    title: "Luật Đất đai 2024"
    sections: ["Điều 45", "Điều 46", "Điều 47"]
  - doc_id: 5678
    doc_number: "43/2014/NĐ-CP"
    title: "Nghị định hướng dẫn Luật Đất đai"
    sections: ["Điều 12", "Điều 13"]
tags: [đất-đai, chuyển-nhượng, quyền-sử-dụng-đất]
created: 2026-05-01
updated: 2026-05-05
created_by_model: "claude-sonnet-4-20250514"
reviewed: true
reviewer: "admin@example.com"
---
```

### 9.4. Ba thao tác cốt lõi

**Ingest (Biên dịch):**

Khi văn bản mới được nhập vào hệ thống, LLM thực hiện:

```
Văn bản mới (VD: Nghị định sửa đổi)
  │
  ├─→ Trích xuất nội dung chính theo Điều/Khoản
  ├─→ Xác định lĩnh vực và chủ đề liên quan
  ├─→ Tóm tắt đa mức (tổng quan + theo Chương)
  ├─→ Phát hiện thay đổi so với quy định cũ
  └─→ Sinh cặp câu hỏi - câu trả lời phổ biến
        │
        ▼
  Cập nhật wiki:
  ├─→ Tạo trang tóm tắt cho văn bản mới
  ├─→ Cập nhật trang chủ đề liên quan
  ├─→ Cập nhật trang lĩnh vực
  ├─→ Thêm liên kết Obsidian ([[backlinks]])
  └─→ Ghi nhật ký vào log.md
```

**Query (Truy vấn):**

Khi người dùng hỏi, tìm kiếm trên wiki (dense, structured) thay vì raw text. Wiki pages đã chứa tri thức tổng hợp từ nhiều văn bản → câu trả lời chính xác và đầy đủ hơn.

**Lint (Bảo trì):**

Tác vụ nền chạy định kỳ:

| Kiểm tra                    | Mô tả                                                         |
|------------------------------|---------------------------------------------------------------|
| Văn bản hết hiệu lực         | Trang wiki dẫn chiếu VB đã hết hiệu lực → đánh dấu cần cập nhật |
| Mâu thuẫn giữa các trang     | Hai trang wiki nói ngược nhau → đánh dấu cần review           |
| Trang mồ côi                 | Trang không có liên kết đến → gợi ý liên kết hoặc archive    |
| Chủ đề thiếu trang           | Thuật ngữ pháp lý được nhắc nhiều nhưng chưa có trang riêng  |
| Liên kết hỏng                | `[[trang-khong-ton-tai]]` → cảnh báo                          |

### 9.5. Vai trò của Obsidian

Obsidian không chỉ là nơi lưu trữ — nó là **môi trường làm việc** cho admin/chuyên viên pháp chế:

| Tính năng Obsidian          | Ứng dụng trong hệ thống                                      |
|-----------------------------|---------------------------------------------------------------|
| **Graph View**              | Xem đồ thị liên kết giữa các văn bản, chủ đề, lĩnh vực     |
| **Backlinks**               | Tự động thấy "văn bản nào liên quan đến trang đang xem"      |
| **Search**                  | Tìm kiếm nhanh trong vault (bổ sung cho search chính)        |
| **Tags**                    | Gắn tag lĩnh vực, trạng thái review                          |
| **Daily Notes**             | Log thay đổi pháp luật hàng ngày                              |
| **Templates**               | Template chuẩn cho trang mới (LLM sử dụng khi compile)       |
| **Community plugins**       | Dataview (query metadata), Kanban (quản lý review queue)      |

### 9.6. Tích hợp Obsidian ↔ Hệ thống

```
┌────────────────┐         Git push/pull         ┌──────────────────┐
│  Obsidian      │ ◄────────────────────────────► │  Wiki Service    │
│  (Admin PC)    │                                │  (Backend)       │
│                │                                │                  │
│  Đọc wiki      │   ← Git pull (auto-sync)       │  LLM compile     │
│  Review AI     │                                │  wiki mới        │
│  Chỉnh sửa    │   → Git push (on save)          │                  │
│  Thêm ghi chú │                                │  Đọc admin edits │
│  Graph view    │                                │  vào DB          │
└────────────────┘                                └──────────────────┘
```

**Quy trình đồng bộ:**

1. **LLM compile wiki** → commit vào Git repo → Obsidian tự pull về
2. **Admin sửa wiki** trong Obsidian → save → auto commit + push → Backend đọc changes, cập nhật DB
3. **Conflict resolution**: LLM không ghi đè edit của admin — merge thông minh hoặc tạo suggestion branch

### 9.7. So sánh với RAG truyền thống

| Tiêu chí                 | RAG truyền thống              | Wiki + RAG (hệ thống này)         |
|---------------------------|-------------------------------|-------------------------------------|
| Xử lý                    | Mỗi lần query                | Một lần khi ingest (biên dịch)      |
| Liên kết chéo             | Ad hoc hoặc bỏ sót           | Có sẵn, LLM + admin duy trì        |
| Phát hiện mâu thuẫn       | Thường bỏ qua                | Phát hiện qua lint                  |
| Tích lũy tri thức         | Reset mỗi query              | Tích lũy qua mỗi lần ingest        |
| Chất lượng trả lời        | Phụ thuộc chunk retrieval    | Dựa trên tri thức đã tinh chế       |
| Human-in-the-loop         | Không                        | Admin review/chỉnh sửa qua Obsidian |
| Sở hữu dữ liệu           | Vector DB opaque              | File markdown đọc được, Git version |

<div style="page-break-after: always;"></div>

## 10. Yêu cầu phi chức năng

### 10.1. Hiệu năng

| Chỉ số                              | Mục tiêu                |
|--------------------------------------|-------------------------|
| Tìm kiếm (không re-rank)             | < 60ms (P95)            |
| Tìm kiếm (có re-rank)                | < 600ms (P95)           |
| Q&A pháp luật (RAG)                   | < 5 giây                |
| Nhập văn bản PDF thông thường         | < 10 giây               |
| Nhập văn bản PDF + phân tích cấu trúc | < 30 giây              |
| Tải trang web portal                  | < 2 giây                |

### 10.2. Khả năng mở rộng (Scalability)

| Thành phần        | Chiến lược mở rộng                                          |
|-------------------|--------------------------------------------------------------|
| Elasticsearch     | Cluster 3+ nodes, sharding theo năm ban hành                |
| Vector DB         | Qdrant cluster hoặc pgvector partitioning                    |
| PostgreSQL        | Read replicas, partitioning theo doc_type                    |
| API Gateway       | Horizontal scaling (stateless), load balancer                |
| Ingestion         | Worker pool, scale theo số nguồn cần crawl                   |
| LLM Service       | Queue-based, auto-scale theo tải                             |

### 10.3. Tính sẵn sàng (Availability)

| Chỉ số   | Mục tiêu | Ghi chú                                        |
|----------|----------|-------------------------------------------------|
| Uptime   | 99.5%    | Cho phép downtime bảo trì ngoài giờ hành chính |
| RTO      | 4 giờ    | Recovery Time Objective                          |
| RPO      | 1 giờ    | Recovery Point Objective                         |

### 10.4. Bảo mật & Riêng tư

| Yêu cầu                | Giải pháp                                                  |
|-------------------------|--------------------------------------------------------------|
| Mã hóa truyền tải       | TLS 1.3 cho mọi kết nối                                     |
| Mã hóa lưu trữ          | Encryption at rest cho database và object storage           |
| Xác thực                 | JWT + OAuth2 (OIDC)                                         |
| Phân quyền               | RBAC: public (đọc VB công khai), editor (quản lý wiki), admin |
| Audit log                | Ghi log mọi truy vấn, thay đổi wiki                        |
| LLM data privacy         | Tùy chọn Ollama local khi xử lý dữ liệu nhạy cảm          |

### 10.5. Khả năng bảo trì

| Yêu cầu                     | Giải pháp                                              |
|------------------------------|--------------------------------------------------------|
| Monitoring                   | Prometheus + Grafana cho metrics hệ thống              |
| Logging                      | ELK stack (Elasticsearch, Logstash, Kibana)            |
| Alerting                     | PagerDuty / Slack alerts cho downtime, lỗi ingestion   |
| CI/CD                        | GitHub Actions / GitLab CI                              |
| Infrastructure as Code       | Terraform / Ansible cho provisioning                    |

<div style="page-break-after: always;"></div>

## 11. Công nghệ sử dụng

| Thành phần                | Công nghệ                        | Lý do chọn                                               |
|---------------------------|----------------------------------|-----------------------------------------------------------|
| Ngôn ngữ backend           | Python 3.11+                     | Hệ sinh thái ML/AI phong phú, thư viện NLP tiếng Việt   |
| API framework              | FastAPI                          | Async, tự động sinh OpenAPI docs, hiệu năng cao          |
| Cơ sở dữ liệu chính       | PostgreSQL 16+                   | ACID, JSONB, quan hệ phức tạp, pgvector extension        |
| Full-text search           | Elasticsearch 8.x               | ICU tokenizer cho tiếng Việt, aggregation, scale ngang   |
| Vector search              | Qdrant hoặc pgvector             | HNSW index, metadata filtering (Qdrant) / đơn giản hóa stack (pgvector) |
| Object storage             | MinIO (on-prem) / S3 (cloud)    | Lưu file gốc, compatible S3 API                          |
| Embedding model            | vietnamese-bi-encoder (768-dim)  | Tối ưu cho tiếng Việt, hiệu năng tốt trên retrieval tasks |
| LLM abstraction            | litellm                          | Giao diện thống nhất cho OpenAI, Anthropic, Ollama        |
| Task queue                 | Celery + Redis                   | Background jobs (AI tasks, wiki compilation, crawling)    |
| Knowledge Wiki             | Obsidian vault + Git             | Markdown native, liên kết chéo, admin-friendly            |
| Web frontend               | Next.js (React)                  | SSR cho SEO, component ecosystem                          |
| Crawler                    | Scrapy                           | Mature, extensible, built-in scheduling                    |
| PDF extraction             | pymupdf4llm / marker-pdf         | Nhanh (bậc 1) + chất lượng cao (bậc 2)                   |
| HTML extraction            | trafilatura                      | F1-score cao cho web content extraction                    |
| Tiếng Việt NLP             | underthesea / vncorenlp           | Tokenization, NER cho tiếng Việt                          |
| Containerization           | Docker + Docker Compose           | Đóng gói các service, dễ deploy                           |
| Orchestration              | Kubernetes (production)           | Auto-scaling, self-healing, rolling updates                |

<div style="page-break-after: always;"></div>

## 12. Lộ trình triển khai

### Phase 1 — MVP: Tìm kiếm cơ bản

**Mục tiêu**: Hệ thống tìm kiếm văn bản hoạt động được, phục vụ nhu cầu tra cứu cơ bản.

- Ingestion pipeline cho nguồn chính (Công báo, vbpl.vn)
- Trích xuất nội dung PDF/HTML → markdown
- Phân tích cấu trúc pháp lý cơ bản (Điều/Khoản)
- Full-text search trên Elasticsearch (BM25)
- Web portal đơn giản (tìm kiếm, xem văn bản)
- API REST cơ bản
- PostgreSQL cho metadata

### Phase 2 — Tìm kiếm thông minh + RAG

**Mục tiêu**: Bổ sung tìm kiếm ngữ nghĩa, hỏi đáp pháp luật, và quan hệ pháp lý.

- Vector search (embedding tiếng Việt + Qdrant/pgvector)
- Hybrid search (BM25 + Vector + RRF)
- Faceted search (loại VB, cơ quan, năm, hiệu lực)
- Trích xuất quan hệ pháp lý (thay thế, sửa đổi, hướng dẫn)
- Q&A pháp luật (RAG pipeline)
- Auto-summarization + auto-tagging
- Ưu tiên hiệu lực trong kết quả tìm kiếm
- Thêm nguồn dữ liệu (cổng Chính phủ, UBND tỉnh/thành)

### Phase 3 — Knowledge Wiki + Obsidian

**Mục tiêu**: Biên dịch tri thức pháp luật thành wiki, admin quản lý qua Obsidian.

- Knowledge Wiki (Karpathy pattern) cho pháp luật
- Obsidian vault + Git sync
- LLM compilation pipeline (ingest, query, lint)
- Admin workflow: review AI-generated wiki trong Obsidian
- Graph view cho quan hệ giữa các văn bản
- Timeline cho lịch sử thay đổi pháp luật theo lĩnh vực
- Mở rộng nguồn dữ liệu (án lệ, bản án)
- Mobile app
- API công khai cho bên thứ ba

<div style="page-break-after: always;"></div>

## 13. Phụ lục

### 13.1. Thuật ngữ

| Thuật ngữ              | Giải thích                                                            |
|------------------------|-----------------------------------------------------------------------|
| BM25                   | Thuật toán xếp hạng full-text search, cải tiến từ TF-IDF              |
| Chunking               | Chia văn bản dài thành các đoạn nhỏ để embedding và retrieval         |
| Cross-Encoder          | Model xếp hạng lại kết quả, chính xác hơn nhưng chậm hơn bi-encoder  |
| Embedding              | Biểu diễn văn bản dưới dạng vector số học trong không gian nhiều chiều |
| Faceted Search         | Tìm kiếm kết hợp lọc theo các thuộc tính (facet) của tài liệu        |
| HNSW                   | Hierarchical Navigable Small World — cấu trúc index cho vector search |
| Knowledge Wiki         | Tri thức đã biên dịch thành markdown có cấu trúc, LLM duy trì        |
| LLM Wiki Pattern       | Kiến trúc của Karpathy: biên dịch tài liệu thành wiki thay vì tìm trên raw text |
| RAG                    | Retrieval-Augmented Generation — truy xuất + sinh câu trả lời         |
| RRF                    | Reciprocal Rank Fusion — thuật toán kết hợp kết quả từ nhiều nguồn    |
| VBQPPL                 | Văn bản Quy phạm Pháp luật                                            |

### 13.2. Cấu trúc phân cấp văn bản pháp luật Việt Nam

```
Phần (Phần thứ nhất, Phần thứ hai, ...)
└── Chương (Chương I, Chương II, ...)
    └── Mục (Mục 1, Mục 2, ...)
        └── Tiểu mục (Tiểu mục 1, ...)
            └── Điều (Điều 1, Điều 2, ...)
                └── Khoản (1., 2., 3., ...)
                    └── Điểm (a), b), c), ...)
```

Không phải mọi văn bản đều có đủ các cấp. Văn bản ngắn (Công văn, Chỉ thị) có thể chỉ có Điều/Khoản hoặc không phân chia.

### 13.3. Các loại quan hệ pháp lý

| Quan hệ              | Ý nghĩa                                                        | Ảnh hưởng hiệu lực       |
|-----------------------|-----------------------------------------------------------------|---------------------------|
| Thay thế              | Văn bản A thay thế hoàn toàn văn bản B                         | B hết hiệu lực            |
| Sửa đổi, bổ sung      | Văn bản A sửa một số Điều/Khoản của B                          | B vẫn hiệu lực, đã sửa   |
| Bãi bỏ                | Văn bản A bãi bỏ một số Điều/Khoản của B                       | Các Điều/Khoản đó hết hiệu lực |
| Hướng dẫn thi hành    | Văn bản A hướng dẫn chi tiết cho B                              | Không ảnh hưởng           |
| Viện dẫn               | Văn bản A tham chiếu đến B để bổ trợ                           | Không ảnh hưởng           |
| Đính chính              | Đính chính lỗi kỹ thuật (sai số, sai chữ) trong B             | B vẫn hiệu lực, đã đính chính |

### 13.4. Tài liệu tham khảo

- Karpathy, A. (2026). *LLM Knowledge Bases.* https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods.* SIGIR '09.
- Elasticsearch Documentation: https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html
- Qdrant Documentation: https://qdrant.tech/documentation/
- Obsidian: https://obsidian.md
- vietnamese-bi-encoder: https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder
- Luật Ban hành văn bản quy phạm pháp luật 2015 (Luật số 80/2015/QH13)
