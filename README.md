# Classroom Digital Twin — A302

Dự án riêng cho lớp học, không thay thế dự án kho trước đó. ESP32/Wokwi đọc
DHT22 và **hai tia hồng ngoại A/B đếm người vào–ra**, điều khiển **4 đèn độc lập và 1 đầu ra quạt**. ThingsBoard trên
AWS lưu dữ liệu, tính sức khỏe lớp học, tạo cảnh báo và gửi lệnh hai chiều.

## Lấy mã nguồn từ GitHub

```powershell
git clone https://github.com/duy-tu2005/classroom-digital-twin.git
cd classroom-digital-twin
Copy-Item .\firmware\secrets.example.h .\firmware\secrets.h
```

Repo không chứa mật khẩu, token thiết bị hay khóa SSH. Điền Wi-Fi, địa chỉ
ThingsBoard và token của thiết bị bạn được cấp vào `firmware/secrets.h` trước
khi build/nạp ESP32. Với Wokwi dùng Wi-Fi mô phỏng; với mạch thật dùng Wi-Fi
2.4 GHz tại nơi chạy. Không commit `secrets.h` lên Git.

Nếu cài một máy chủ ThingsBoard mới, làm theo
[hướng dẫn triển khai](docs/run-and-restore.md); `deployment/.env.example`
là mẫu cấu hình, không phải mật khẩu của server hiện tại. File báo cáo,
backup và ảnh tham khảo cá nhân được giữ riêng, không nằm trong repo mã nguồn.

## Dashboard AWS

- Server: **http://3.104.115.21** (Elastic IP, gắn cố định vào EC2 `iot_lab`).
- Dashboard: [Classroom A302](http://3.104.115.21/dashboards/4d30d200-c6c8-11f1-b568-efad131da3da)
- Tenant admin: `classroom@thingsboard.org`
- Mật khẩu riêng: dòng `TB_PASSWORD` trong `deployment/.env`.

IP cũ `16.178.88.226` và `54.206.35.208` không còn dùng. PostgreSQL và ThingsBoard chạy trong
Docker trên EC2; laptop không cần chạy Docker. Firmware/Wokwi cần chạy và
có mạng để dữ liệu cập nhật và nhận lệnh.

## Chức năng

- Ảnh lớp học nhìn chéo từ góc trên cao, nền trong suốt, bỏ tường bên phải
  và viền tường thấp; dùng đúng bản người dùng đã duyệt.
- Đèn 1/2/3/4 tạo **4 dải ngang song song từ tường trái sang tường phải**,
  đánh số từ phía bảng đến cuối lớp. Ánh sáng đổi theo telemetry phản hồi,
  có mép mềm và lan sáng nhẹ. Đèn 1 phủ cả bảng/tường phía trước; bốn dải
  ghép kín toàn bộ lớp (bàn, sàn, tường), bật hết không còn khoảng tối do mask.
- Đếm số người trong phòng, tổng lượt vào/ra; xem trạng thái hai tia A/B và
  lịch sử số người trên ThingsBoard. Có xác nhận phòng trống để hiệu chuẩn.
- Quạt AUTO: bật khi số người >0, giữ 15 giây sau người cuối ra.
  MANUAL: bật/tắt từ dashboard.
- DHT22 đo nhiệt độ, độ ẩm mỗi 5 giây; có biểu đồ nhiệt độ, RSSI và sức khỏe.
- Cảnh báo nhiệt độ cao/thấp, cảm biến lỗi, Wi-Fi yếu, phản hồi đầu ra lệch
  lệnh và mất kết nối. Nút điều khiển khóa khi ESP32 ngoại tuyến.

Mạch Wokwi đã bỏ relay: LED xanh qua điện trở 220Ω nối GPIO23 mô phỏng
đầu ra quạt, chưa đo tốc độ quay thực tế. Không nối động cơ quạt thật
trực tiếp vào GPIO; phần cứng thật cần tầng công suất riêng. PIR đã được bỏ.
Wokwi dùng hai **nút nhấn A/B giả lập đầu ra chắn tia**, không phải cảm biến
quang học thật. Phần cứng dùng hai bộ phát–thu cắt tia (tổng 4 đầu).
Dự án hiện không có cảm biến CO₂, lux hay điều hòa.

## Chạy Wokwi

Từ thư mục dự án:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\build.ps1
code D:\classroom_fw
```

Trong cửa sổ VS Code của firmware: **F1 → Wokwi: Start Simulator**. Giữ tab
Simulator hiển thị trong lúc thử; terminal cần báo `RPC subscribe=OK` và
`sequence` tăng mỗi 5 giây. Nếu IP/token thay đổi, phải build lại trước khi
restart. License Wokwi hết hạn cần gia hạn trên trang chính thức.

Firmware hiện tại `2.0.1`. Chân GPIO16/17 trên board Wokwi này có tên
`RX2`/`TX2`, **không phải `D16`/`D17`**. Mỗi lần build đều kiểm tra tên chân,
điện trở nối tiếp và đường GND của cả 5 LED trước khi biên dịch.

## Cấu trúc

```text
classroom-digital-twin/
├── assets/                 # Phối cảnh lớp học và ảnh tham khảo
├── firmware/               # ESP32, sơ đồ Wokwi, script build
├── thingsboard/
│   ├── api.py              # REST client và tạo tenant
│   ├── setup.py            # Bootstrap mô hình/dashboard idempotent
│   ├── rule-scripts/       # Sức khỏe, trạng thái, expected/observed, alarm
│   ├── widgets/            # HTML/CSS/JS và hình học 4 dải sáng ngang lớp
│   └── exports/            # JSON mô hình được triển khai
├── deployment/             # Docker Compose, cấu hình, deploy AWS
├── tests/                  # Unit test rule và kiểm thử RPC/pipeline AWS
├── tools/                  # Preview và chụp dashboard để kiểm tra giao diện
└── docs/                   # Kiến trúc và hướng dẫn chạy/khôi phục
```

Source trên AWS: `/opt/classroom-digital-twin`. Stack ThingsBoard hiện dùng
chung server với dự án kho nhưng lớp học có tenant, Device và Rule Chain riêng.
Các file `.env`, `.env.local`, `secrets.h` và khóa SSH là dữ liệu riêng,
không đưa lên Git hay chia sẻ công khai.

## Tài liệu và kiểm thử

- [Kiến trúc, luồng dữ liệu và vì sao là Digital Twin](docs/architecture.md)
- [Chạy demo, triển khai Docker và khôi phục từ đầu](docs/run-and-restore.md)
- [Thông tin triển khai và kết quả kiểm thử](docs/deployment-status.md)
- [Đếm người hai tia A/B: đấu nối, thuật toán và cách thử](docs/people-counter.md)
- `node tests/rules.test.cjs`: kiểm thử các rule xử lý dữ liệu.
- `python tests/wiring_test.py`: kiểm tra chân Wokwi và mạch kín của 5 LED.
- `node tests/lighting.test.cjs`: ảnh được duyệt và 4 dải chạy theo phối cảnh.
- `node tests/occupancy-panel.test.cjs`: kiểm tra giao diện số người bằng
  Chrome chạy nền, chỉ dùng dữ liệu thử trong trình duyệt, không kết nối AWS.
  Cài thư viện Node cho bài này bằng `npm install --no-save playwright`
  và cần có Google Chrome trên máy.
- `python tests/aws_pipeline.py`: dùng MQTT client QA và entity tạm trên AWS
  để kiểm tra widget, RPC, Rule Engine và alarm; tự dọn entity QA.
- `python tests/live_rpc.py`: kiểm tra firmware Wokwi đang chạy; trả đầu ra
  về trạng thái ban đầu. Kiểm thử QA không thay thế kiểm thử Wokwi này.

Phần kiểm thử giao diện cần Chrome và thư viện được mô tả trong hướng dẫn.
