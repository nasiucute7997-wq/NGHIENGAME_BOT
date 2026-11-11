# OKOTP Telegram Bot - bộ khung khởi đầu

Bot Telegram Python + Aiogram 3 + SQLite. Có menu, tài khoản, số dư, danh sách dịch vụ, tạo đơn, yêu cầu nạp thủ công và quản trị.

## Cấu hình Railway
Thêm các Variables:
- BOT_TOKEN: token BotFather cấp (không đưa token vào GitHub)
- ADMIN_IDS: 6369714149
- SUPPORT_USERNAME: username hỗ trợ, không bắt buộc
- DB_PATH: /data/bot.db nếu đã gắn Railway Volume tại /data; nếu không, dùng bot.db (có thể mất dữ liệu khi redeploy)

## Lệnh người dùng
/start, /menu, /services, /balance, /deposit, /nap 50000, /orders

## Lệnh admin
/admin, /addservice Tên dịch vụ|Giá, /delservice ID, /duyetnap ID, /huy nap ID, /setbalance USER_ID SỐ_TIỀN, /stats

## Chạy local
pip install -r requirements.txt
python main.py

## Triển khai
Tạo Railway service từ repository, đặt Variables, sau đó Deploy. Đây là worker chạy polling, không cần domain.

## Tích hợp API OTP
Hiện tại đơn được lưu trạng thái pending; chưa gọi API nhà cung cấp. Cần tài liệu API chính thức của nhà cung cấp được phép sử dụng (endpoint, xác thực, mã dịch vụ, lấy OTP, hủy/hoàn tiền). Không lưu API key trong source code. Chỉ dùng cho xác minh tài khoản/dịch vụ bạn có quyền sử dụng; không dùng để vượt xác thực hay truy cập tài khoản người khác.
