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


## Quản lý nút menu bằng quyền Admin

Mở bot và gửi `/admin`. Admin có thể quản lý menu ngay trong Telegram:

- `/buttonlist` — xem danh sách nút và ID.
- `/buttonadd Tên nút|callback/url/message|Giá trị` — thêm nút.
- `/buttonedit ID|Tên mới|callback/url/message|Giá trị mới` — sửa nút.
- `/buttondel ID` — xóa nút.

Loại `callback` dùng một mục có sẵn: `sites`, `cat:GAME`, `minigames`, `other_services`, `account`, `deposit`, `orders`, `guide`, `support`, `home`. Loại `url` mở liên kết HTTP/HTTPS. Loại `message` gửi nội dung văn bản do Admin nhập.

Ví dụ:

```
/buttonadd 🌐 WEBSITE|url|https://example.com
/buttonadd 📣 THÔNG BÁO|message|Nội dung thông báo
```

Menu mặc định được tạo tự động khi khởi động lần đầu. Với database cũ, bot tự thêm bảng menu mà không xóa dữ liệu người dùng, đơn hàng hoặc số dư. Hãy giữ nguyên Volume và `DB_PATH` hiện tại để không mất dữ liệu SQLite.

## Chạy trên hosting

Lệnh khởi động: `python main.py` (Procfile cũng khai báo worker). Cấu hình `BOT_TOKEN`, `ADMIN_IDS`, `DB_PATH` trong mục Environment Variables của hosting. Chỉ chạy một tiến trình polling cho mỗi BOT_TOKEN.
