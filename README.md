# NGHIEN CODE BOT

Telegram bot chạy trực tiếp từ thư mục gốc repository bằng Python và Aiogram 3.

## Railway setup

Cấu hình service Railway:
- **Root Directory:** để trống (repository root).
- **Start Command:** `python main.py`.
- **Build Command:** để Railway tự cài các gói trong `requirements.txt`, hoặc dùng `pip install -r requirements.txt`.

Thiết lập Variables trong Railway:
- `BOT_TOKEN`: token bot lấy từ BotFather (không đưa token lên GitHub).
- `ADMIN_IDS`: `6369714149`.
- `SUPPORT_USERNAME`: username hỗ trợ, không bắt buộc.
- `DB_PATH`: `/data/bot.db` để dùng database trên Volume.

Gắn Railway Volume vào đường dẫn `/data` để giữ dữ liệu SQLite qua các lần triển khai. Nếu trước đây bot đã dùng Volume `/data` và `DB_PATH=/data/bot.db`, hãy giữ nguyên Volume và biến này để tiếp tục dùng dữ liệu hiện tại.

## Cấu trúc chạy

- `main.py`: mã nguồn bot chính tại thư mục gốc.
- `requirements.txt`: thư viện Python.
- `config.py`: tệp cấu hình cũ, không còn được import bởi mã nguồn chính.
- `okotp_bot/`: giữ lại bản mã nguồn cũ để đối chiếu; Railway không chạy thư mục này.

## Lưu ý bảo mật và vận hành

- Không commit `.env`, BOT_TOKEN hoặc thông tin bí mật lên GitHub.
- Bot có quy trình tạo yêu cầu dịch vụ, nhập tên tài khoản và gửi ADMIN xác nhận.
- Các đơn cần ADMIN duyệt mới được xử lý; tự động thực hiện dịch vụ cần API chính thức từ nhà cung cấp.
- Chỉ lưu tên tài khoản; không yêu cầu người dùng gửi mật khẩu hoặc OTP.
