# Lộ Trình Công Việc Cho Trưởng Nhóm (Core Admin)

Tài liệu này liệt kê chi tiết các đầu việc bạn cần làm để xây dựng "khung xương" vững chắc cho Bot.

## Giai Đoạn 1: Khởi Tạo Dự Án (Project Setup) - 🟢 Đã Xong

- [x] Tạo cấu trúc thư mục chuẩn.
- [x] Cấu hình Git & GitHub (Main/Dev).
- [x] Thiết lập quy trình làm việc nhóm (`CONTRIBUTING.md` / `README.md`).

## Giai Đoạn 2: Xây Dựng Lõi (Core Framework) - 🔴 Ưu Tiên Cao nhất

Đây là phần quan trọng nhất, Bot sống hay chết là ở đây. Bạn cần code xong cái này thì thành viên mới có chỗ để lắp skill vào.

### 1. Quản lý Cấu hình (`config/`)
- [ ] Tạo file `settings.yaml`: Chứa các setting mặc định (Timezone, Log level).
- [ ] Code `config/loader.py`: Class để đọc file yaml và `.env` (dùng thư viện `python-dotenv`).

### 2. Thiết kế Cơ sở dữ liệu (`database/`)
- [ ] Chọn DB: SQLite (cho dev) hoặc PostgreSQL (cho production).
- [ ] Code `models.py`: Định nghĩa các bảng (Tables).
    - `User`: Lưu thông tin người dùng Telegram.
    - `Task`: Lưu lịch sử các việc bot đã làm.
    - `Memory`: Lưu ngữ cảnh chat (nếu dùng AI).
- [ ] Code `storage.py`: Class quản lý kết nối (Session Manager), hàm `save_user`, `get_user`.

### 3. Động Cơ Chính (`core/engine.py`)
- [ ] Code `Engine` class: Vòng lặp vô tận (While True) nhưng dùng `asyncio` để không bị đơ.
- [ ] Tích hợp `TaskQueue`: Để xử lý việc nặng (VD: download video) ở background mà không làm bot bị lag khi chat.

---

## Giai Đoạn 3: Tích Hợp & Review (Integration) - 🟡 Ongoing

Sau khi có Lõi, bạn sẽ đóng vai trò "Người gác cổng" (Gatekeeper).

- [ ] **Review Pull Request**:
    - Kiểm tra code của thành viên có sạch không?
    - Có quên xóa `print()` không?
    - Có hard-code token không?
- [ ] **Merge Code**: Hợp nhất tính năng của thành viên vào nhánh `dev`.
- [ ] **Xử lý xung đột (Conflict)**: Nếu 2 người cùng sửa 1 file, bạn là người quyết định giữ dòng nào.

---

## Giai Đoạn 4: Vận Hành (DevOps & Deploy) - 🔵 Sau Khi Hoàn Thiện

Khi Bot đã chạy ổn định ở local.

- [ ] **Docker hóa**:
    - Viết `Dockerfile`: Đóng gói mọi thứ vào container.
    - Viết `docker-compose.yml`: Để chạy cả Bot và Database cùng lúc.
- [ ] **Server Setup** (VPS):
    - Cài Docker trên VPS.
    - Setup CI/CD (nếu muốn tự động deploy khi push code).
- [ ] **Monitoring**:
    - Gắn log để báo lỗi về Telegram cá nhân của bạn khi bot bị crash.

---

## Checklist Cần Làm Ngay (Tuần này)
1. Code xong file `config/loader.py`.
2. Dựng xong `database/models.py`.
3. Viết khung sườn cho `core/engine.py`.
