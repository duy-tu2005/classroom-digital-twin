# Bàn giao triển khai — cập nhật 18/10/2026

## Điểm truy cập

- AWS EC2 `iot_lab`, region `ap-southeast-2`, Elastic IP `3.104.115.21`.
- [Dashboard lớp học](http://3.104.115.21/dashboards/4d30d200-c6c8-11f1-b568-efad131da3da).
- Tenant `Classroom Digital Twin`, tài khoản `classroom@thingsboard.org`.
- Mật khẩu tại `deployment/.env`, khóa `TB_PASSWORD`; không lưu trong tài liệu.
- Source server: `/opt/classroom-digital-twin`.
- PostgreSQL và ThingsBoard CE 4.3.1.5 dùng Docker stack có sẵn tại
  `/opt/produce-warehouse-digital-twin`; tenant kho cũ được giữ nguyên.

## Cập nhật bộ đếm người — firmware 2.0.1

PIR đã bỏ khỏi sơ đồ/firmware/dashboard. Hai nút A/B trong Wokwi mô phỏng
đầu ra active LOW của hai bộ hồng ngoại cắt tia, lần lượt GPIO13 và GPIO27.
ThingsBoard đã nhận telemetry firmware 2.0.1; View PIR đổi thành
`Classroom_PeopleCounter_View`, giữ ID của View cũ. Có số người, tổng vào/ra,
trạng thái tia, nút xác nhận phòng trống và biểu đồ lịch sử số người.
Ảnh được duyệt và bốn dải sáng không thay đổi.

| Kiểm thử mới 15/10 | Kết quả | Phạm vi |
|---|---|---|
| Build firmware 2.0.1 | PASS | ESP32, 45.016 byte RAM / 767.165 byte flash |
| Thuật toán C++ thực | PASS | Vào/ra, quay đầu, bỏ bước, dội nút, timeout, không âm, wrap millis; ASan/UBSan |
| Mạch Wokwi | PASS | 3 unit test, lint không lỗi/cảnh báo, hai nút đúng GPIO/GND |
| RPC firmware 2.0.1 | PASS | Bốn đèn độc lập và quạt, trả đầu ra về ban đầu |
| Dữ liệu bộ đếm trên AWS | PASS | Client QA riêng: Device → Rule Chain → Asset → widget |
| Tia và hiệu chuẩn trên widget | PASS | Hiện tia, khóa reset khi chắn, hủy/xác nhận reset đúng |
| So sánh lệnh/đầu ra | PASS | Lưu intent theo kênh, timestamp hợp lệ, tạo mismatch và phục hồi |
| Giao diện/ánh sáng/Alarm | PASS | Preview, mobile, pipeline AWS mới; xem báo cáo JSON |
| Wokwi đếm vào | NGƯỜI DÙNG XÁC NHẬN | Đã thấy tăng lên 1; không coi là đo cảm biến quang học thật |

`tests/results/aws-pipeline.json` là báo cáo QA mới (không publish vào Device
Wokwi chính). `tests/results/live-rpc.json` là bài RPC trên firmware 2.0.1.
Lần đọc sau một lần restart cho thấy 0 người/chưa hiệu chuẩn: Wokwi có thể
reset flash khi bắt đầu lại, nên không được giả định số cũ luôn được giữ.
Đọc hướng dẫn [hai tia và hiệu chuẩn](people-counter.md) trước khi demo.
AUTO dùng số người, giữ 15 giây sau người cuối ra; MANUAL vẫn hoạt động.
2.0.1 thêm mutex riêng cho ghi NVS, tránh snapshot cũ ghi đè lệnh hiệu
chuẩn khi trùng thời điểm với một lượt qua cửa; không đổi sơ đồ/thuật toán.

Đã sửa báo sai ACTUATOR_MISMATCH do coi expected timestamp=0 là lệnh thật.
Widget lưu expected state qua REST đã xác thực trước RPC; bỏ qua expected
quạt trong AUTO. Đây vẫn là phản hồi GPIO, chưa phải đo dòng/tốc độ/lux thật.

Backup database trước nâng cấp:
`/opt/classroom-digital-twin/deployment/backups/pre-ir-counter-20261015.sql.gz`
(24 MB, đã kiểm tra gzip). Backup gồm dữ liệu các tenant dùng chung, cần giữ riêng.
Không xóa Device/Asset, lịch sử hay Docker volume; không restart stack kho cũ.

## Kết quả trước cập nhật bộ đếm (lưu để đối chiếu)

Bản giao diện hiện tại dùng ảnh góc trên cao đã duyệt, bỏ tường phải và
viền tường thấp, nền trong suốt. Bốn đèn tạo bốn dải ngang song song, từ
tường trái sang tường phải, đánh số 1–4 từ phía bảng đến cuối lớp.
Đèn 1 chiếu sáng cả bảng và tường trước. Phiên bản 4 ghép các dải thành
một mask chung; bật hết phủ kín 100% ảnh, không còn khoảng tối do mask.

| Kiểm thử | Kết quả | Phạm vi |
|---|---|---|
| PlatformIO build ESP32 | PASS | Firmware biên dịch với IP và token lớp học |
| Rule script scenarios | PASS | Ngưỡng, recovery, offline, mismatch và tách kênh |
| Sơ đồ điện 5 LED | PASS | Wokwi CLI lint không lỗi/cảnh báo; 3 bài test chân và mạch kín |
| RPC 4 đèn | PASS | Firmware 1.0.1: bật riêng, phản hồi đúng GPIO16/17/18/19 và telemetry |
| RPC quạt | PASS | Firmware 1.0.1: bật/tắt MANUAL và chuyển AUTO |
| Quan sát LED Wokwi | ĐÃ XÁC NHẬN | Người dùng xác nhận LED vàng và LED xanh sáng/tắt đúng ngày 15/10 |
| Ảnh và hình học 4 dải ngang | PASS | Đúng ảnh được duyệt, mỗi dải chạy trọn chiều ngang lớp |
| Đèn 1 phủ toàn bộ bảng | PASS | Các điểm kiểm tra trên bảng đều đạt alpha=255 |
| 16 tổ hợp bật/tắt | PASS | Preview: tâm mỗi dải sáng đúng theo kênh, không ảnh hưởng dải tắt |
| 4 dải sáng trên AWS | PASS | Widget thực, MQTT client QA độc lập |
| Bật đồng thời 4 dải | PASS | 4 đầu ra phản hồi đúng; 262.144 điểm mask đều alpha=255 |
| WebSocket thời gian thực | PASS | Không ngắt trong bài kiểm thử widget |
| HIGH_TEMPERATURE | PASS | Rule Engine AWS, tạo alarm ở 35°C, health=10 |
| Phục hồi | PASS | Rule Engine AWS, về NORMAL và clear alarm |
| CONNECTION_LOST | PASS | Rule Engine AWS, khi QA dừng telemetry |
| Giao diện mobile | PASS | Preview 420px, chữ/công tắc không tràn hoặc chồng nhau |

Kết quả chi tiết: `tests/results/live-rpc.json` và
`tests/results/aws-pipeline.json` trên máy local. Bài QA tạo Device/Asset/
Dashboard tạm trong tenant lớp học, rồi xóa các entity đó; không giả dữ liệu
cho Device Wokwi chính. RPC thực trả đầu ra về trạng thái ban đầu.
Pipeline QA giao diện/rule là kết quả 13/10 sau cập nhật mask phiên bản 4.
Ngày 15/10 sửa tên chân sai `D16/D17` thành `RX2/TX2`, bỏ relay đỏ và nối
LED xanh trực tiếp qua điện trở ở GPIO23. Firmware 1.0.1 bổ sung version,
GPIO và `pin_state` trong RPC response để phân biệt firmware cũ.
Bài RPC mới nhất đã đạt và trả đầu ra về trạng thái ban đầu; người dùng
đã xác nhận nhìn thấy LED trong Wokwi sáng/tắt đúng. Báo cáo tự động vẫn
ghi rõ phạm vi RPC/GPIO + sơ đồ tĩnh, không giả nhận là đo sáng quang học.
Lần thử đầu có một RPC timeout, lần chạy lại hoàn tất cả đèn/quạt và restore.
Kết quả QA và Wokwi được lưu riêng, không coi client QA là firmware Wokwi.

![Kiểm thử 4 dải sáng đồng thời trên AWS bằng Device QA](screenshots/qa-aws-all-lights.png)

## Lưu ý vận hành

- Giữ Wokwi chạy khi muốn điều khiển. Server sống không có nghĩa firmware
  mô phỏng trên laptop cũng đang chạy.
- AUTO hiện dựa vào số người, không còn PIR. Hai tia phải thông trước khi
  bắt đầu lượt mới; chỉ xác nhận phòng trống khi thực sự không còn ai.
  LED xanh biểu diễn đầu ra, không phải cảm biến tốc độ quạt.
- Sửa rule/widget phải chạy bootstrap để cập nhật ThingsBoard.
- Biểu đồ 1 giờ dùng bước 15 giây (240 khoảng); bước 5 giây tạo 720 khoảng,
  vượt giới hạn server và có thể ngắt WebSocket của cả dashboard.
- Elastic IP đã được gắn vào EC2 ngày 18/10/2026. IP giữ nguyên qua stop/start
  khi vẫn giữ allocation và association. Thông tin ở `deployment/elastic-ip.json`.
  Không release IP hoặc gỡ khỏi instance khi chỉ muốn tạm dừng server.
  AWS tính phí IPv4 theo giờ, kể cả lúc instance dừng. Firmware đã đổi host;
  cần nạp binary đã build lại và chạy lại Wokwi để nối tới IP mới.
- Hiện truy cập HTTP/MQTT không TLS; dùng cho demo, không truyền dữ liệu
  nhạy cảm. Nên bổ sung HTTPS/MQTTS và giới hạn SSH trước khi dùng thực tế.
- Không chạy `docker compose down -v`; thao tác này xóa volume database.

Xem [kiến trúc](architecture.md) và [chạy/khôi phục](run-and-restore.md).
