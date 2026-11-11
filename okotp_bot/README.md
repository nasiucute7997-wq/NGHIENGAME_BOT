# NGHIỆN CODE BOT

Telegram bot dùng Python, Aiogram 3 và SQLite.

## Danh mục người dùng
- CODE GAME: sản phẩm thuộc nhóm GAME.
- MINIGAME LIVE: XX8, AD88, U888, ABC8, MM88, RR88, XX88, GG88.
- Minigame đặc biệt: HI88 (Thứ 5), QQ88 (Thứ 6).
- DỊCH VỤ KHÁC: SMS và PRX.
- Tài khoản, nạp tiền thủ công, lịch sử đơn, hướng dẫn và hỗ trợ.

## Cài đặt
1. Tạo bot bằng BotFather và lấy token.
2. Cài Python 3.11+.
3. Chạy:
   \`pip install -r requirements.txt\`
4. Tạo file \`.env\` từ \`.env.example\` và điền BOT_TOKEN.
5. Chạy \`python main.py\`.

Không commit file \`.env\` hoặc token lên GitHub.

## Railway
- Root Directory: \`/okotp_bot\`
- Start Command: \`python main.py\`
- Variables:
  - \`BOT_TOKEN\`: token mới từ BotFather
  - \`ADMIN_IDS=6369714149\`
  - \`SUPPORT_USERNAME\`: username hỗ trợ (không bắt buộc)
  - \`DB_PATH=/data/bot.db\`
- Gắn Railway Volume tại \`/data\` để giữ database qua các lần deploy.

## Lệnh Admin
- \`/addservice GAME|Tên code|Giá\`
- \`/addservice SMS|Tên dịch vụ|Giá\`
- \`/addservice PRX|Tên proxy|Giá\`
- \`/delservice ID\`
- \`/addroom BRAND|Tên phòng|YYYY-MM-DD HH:MM\`
- \`/roomstatus ID|open\` (hoặc \`closed\`, \`full\`)
- \`/result ID|Nội dung kết quả\`
- \`/roomsadmin\`
- \`/duyetnap ID\`
- \`/huy nap ID\`
- \`/setbalance USER_ID SỐ_TIỀN\`
- \`/stats\`

BRAND hợp lệ: XX8, AD88, U888, ABC8, MM88, RR88, XX88, GG88, HI88, QQ88.

## Giới hạn tích hợp
Bot đã có danh mục, đơn hàng, tài khoản, nạp thủ công và quản lý phòng Minigame. Nhà cung cấp SMS, proxy, cổng thanh toán và hệ thống giao code tự động chưa được tích hợp; các đơn sản phẩm được tạo ở trạng thái pending để Admin xử lý. Chỉ kết nối nhà cung cấp hợp pháp, có quyền phân phối và API chính thức. SMS chỉ dùng cho số/SIM thuộc quyền sở hữu hoặc được ủy quyền và cho mục đích xác minh hợp lệ.
