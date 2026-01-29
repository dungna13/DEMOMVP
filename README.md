# CleanBot - Hệ thống Tự động hóa

Dự án Bot tự động hóa (Auto-Bot) phục vụ công việc Clean & Summarize.

## 👥 Thành viên & Quy trình
Dự án gồm 3 thành viên. Quy trình làm việc đơn giản hóa như sau:

1.  **Nhánh Chính (`main`)**: Chỉ chứa code đã kiểm duyệt, chạy ổn định.
2.  **Nhánh Tính năng (`feature/...`)**: Mỗi khi làm chức năng mới, hãy tạo nhánh này.

### Cách đóng góp code (Workflow)
1.  Từ nhánh `main`, tạo nhánh mới: `git checkout -b feature/tên-tính-năng`.
2.  Code và Commit bình thường.
3.  Đẩy lên GitHub: `git push origin feature/tên-tính-năng`.
4.  Tạo **Pull Request** từ `feature/...` vào `main`.
5.  Review và Merge.

## 📂 Cấu trúc Dự án
Tất cả code nằm trong thư mục `auto-bot/`.

```text
CV/
├── auto-bot/           # Source code chính
│   ├── main.py         # File chạy chính
│   ├── requirements.txt# Thư viện cần thiết
│   └── ...
└── README.md           # Hướng dẫn này
```

## 🚀 Cài đặt & Chạy
1.  Cài đặt thư viện:
    ```bash
    pip install -r auto-bot/requirements.txt
    ```
2.  Chạy Bot:
    ```bash
    python auto-bot/main.py
    ```
