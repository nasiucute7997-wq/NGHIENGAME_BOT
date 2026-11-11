# Kiến trúc NGHIỆN CODE BOT

- `main.py`: điểm chạy bot, menu, callback và lệnh Admin.
- `database.py`: dành cho bước tách lớp truy cập dữ liệu tiếp theo; hiện schema được khởi tạo trong `main.py`.
- `handlers/`: dự kiến tách từng nhóm chức năng khi mở rộng.
- `services/`: adapter nhà cung cấp thanh toán, SMS, proxy và giao code; chưa cấu hình thông tin nhà cung cấp.
- SQLite lưu người dùng, số dư, sản phẩm, đơn hàng, nạp tiền, phòng Minigame và lượt đăng ký.

Các đơn dịch vụ cần Admin xác nhận/giao thủ công cho tới khi tích hợp API chính thức.
