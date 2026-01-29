# Auto-Bot Project (Cleanbot)

Dự án phát triển Bot tự động hóa hoạt động 24/7, tích hợp Telegram để điều khiển và giám sát. Bot được thiết kế theo kiến trúc module, dễ dàng mở rộng và bảo trì.

## Cấu trúc Dự án

```text
auto-bot/
├── config/
│   ├── settings.yaml       # Cấu hình chung (Global config)
│   └── secrets.env         # Biến môi trường (Token, API Key - KHÔNG COMMIT FILE NÀY)
├── core/
│   ├── engine.py           # Bộ não trung tâm, vòng lặp xử lý chính
│   ├── task_queue.py       # Hàng đợi ưu tiên (đa nhiệm)
│   ├── scheduler.py        # Lập lịch chạy task (cron job)
│   └── memory.py           # Quản lý ngữ cảnh (RAM & Database)
├── interfaces/
│   └── telegram_bot.py     # Giao diện điều khiển qua Telegram
├── skills/
│   ├── network_scanner.py  # Chức năng quét mạng
│   ├── file_manager.py     # Quản lý file
│   └── web_search.py       # Tìm kiếm thông tin
├── database/
│   ├── models.py           # Định nghĩa cấu trúc dữ liệu (ORM)
│   └── storage.py          # Kết nối CSDL
├── main.py                 # File chạy chính
├── requirements.txt        # Thư viện cần thiết
└── Dockerfile              # Cấu hình để chạy 24/7
```

## Phân Chia Công Việc (Nhóm 2 Người)

Để tối ưu hóa cho team 2 người, công việc được chia theo thế mạnh và chức năng để tránh va chạm code (conflict).

### 🟢 1. Trưởng Nhóm (Bạn - Admin/Core)
Chịu trách nhiệm về "Khung xương" và sự ổn định của Bot.
- **Thiết kế kiến trúc system**: Quyết định cách các module nói chuyện với nhau.
- **Core Engine**: Viết `engine.py`, `task_queue.py` (xử lý đa luồng).
- **Database**: Thiết kế `models.py` và quản lý dữ liệu.
- **Code Review**: Kiểm tra code của thành viên trước khi merge vào `dev`.
- **DevOps**: Cấu hình Docker, Server để bot chạy 24/7.

### 🔵 2. Thành viên (Skill Developer)
Chịu trách nhiệm về "Kỹ năng" và "Giao diện" của Bot.
- **Phát triển Skills**: Viết các file trong thư mục `skills/` (VD: tool download video, tool tóm tắt, tool search).
- **Telegram Interface**: Viết menu, các lệnh `/start`, `/help` để người dùng tương tác.
- **Testing**: Test các chức năng mới tạo xem chạy ổn không.

---

## Quy Trình Làm Việc (Git Workflow)

Chúng ta tuân thủ quy trình **Git Flow** đơn giản nhưng nghiêm ngặt để đảm bảo code không bị lỗi.

### Nhánh (Branches)
- `main`: Phiên bản ổn định nhất (Production). Không commit trực tiếp vào đây.
- `dev`: Phiên bản đang phát triển (Development). Toàn bộ code mới sẽ hợp nhất tại đây.
- `feature/...`: Nhánh tính năng riêng của từng người.

### Các bước thực hiện (Step-by-step)

Mỗi khi bắt đầu làm một tính năng mới (Ví dụ: Làm chức năng login), hãy làm theo đúng thứ tự sau:

#### Bước 1: Đồng bộ code mới nhất
```bash
git checkout dev
git pull origin dev
```

#### Bước 2: Tạo nhánh riêng để làm việc
Đặt tên nhánh theo format: `feature/ten-tinh-nang`
```bash
git checkout -b feature/login
```

#### Bước 3: Code và Commit
Làm việc xong thì lưu lại.
```bash
git add .
git commit -m "Them chuc nang login cho bot"
```

#### Bước 4: Đẩy lên GitHub
```bash
git push origin feature/login
```

#### Bước 5: Tạo Pull Request (PR)
- Lên trang GitHub của dự án.
- Github sẽ hiện nút **"Compare & pull request"**.
- Bấm vào, chọn merge từ `feature/login` vào `dev`.
- **Trưởng nhóm** sẽ vào xem (Review), nếu ổn thì bấm **Merge**.

---

## Lưu ý quan trọng
1. **Tuyệt đối không push thẳng vào `main`**.
2. **File `.env`**: Chứa mật khẩu/Token, tuyệt đối không commit lên Git (đã chặn trong `.gitignore`). Mỗi người tự tạo file `.env` trên máy mình.
3. **Commit Message**: Viết rõ ràng (Ví dụ: "Fix lỗi không connect được database" thay vì "fix bug").
