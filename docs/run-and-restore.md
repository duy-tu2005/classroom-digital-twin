# Chạy, triển khai và khôi phục

## Chạy Wokwi sau khi triển khai

1. Mở thư mục `firmware` bằng VS Code.
2. Gia hạn license nếu hiện License expired: F1 → Wokwi: Request a new License,
   đăng nhập Wokwi, chọn GET YOUR LICENSE và xác nhận mở Visual Studio Code.
3. Build từ thư mục gốc:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\build.ps1
```

4. F1 → Wokwi: Start Simulator. Giữ tab Simulator hiển thị khi kiểm tra.
5. Terminal phải báo `[MQTT] connected | RPC subscribe=OK` và `sequence` tăng
   sau mỗi 5 giây. Chỉ sửa `secrets.h` rồi restart mà không rebuild sẽ dùng
   lại IP/token cũ trong firmware.bin.

Sau cập nhật đếm người 15/10/2026, dòng khởi động phải là `[BOOT] Classroom 2.0.1`.
Nếu vẫn thấy relay đỏ hoặc nhãn đèn cũ, dừng mô phỏng, lưu `diagram.json`
đúng dự án lớp học rồi Start Simulator lại; build không tự reload sơ đồ
của mô phỏng đang chạy. Không chạy đồng thời nhiều bản mô phỏng cùng token.

Hai chân đèn đầu là `esp32:RX2` và `esp32:TX2` (GPIO16/17); tên `D16` và
`D17` không tồn tại trên model board này. Cả 5 LED đều phải có anode qua
điện trở, cathode về GND. Riêng chân `NC` của DHT22 cố ý không nối.

## Demo

- Bật riêng từng đèn trên dashboard: dải tương ứng sáng ngang từ tường trái
  sang tường phải (đèn 1 gần bảng, đèn 4 cuối lớp) và LED của kênh
  đó sáng trong Wokwi. Có thể bật nhiều vùng cùng lúc.
- Đèn 1 phải sáng cả bảng phía trước. Bật cả 4 đèn phải sáng toàn bộ ảnh
  lớp học, không còn khe tối do mặt nạ giữa các dải.
- Bật/tắt quạt thủ công; LED xanh nối GPIO23 thể hiện đầu ra quạt, không còn relay.
- Chọn Tự động theo số người. Khi phòng trống và hai tia thông, bấm
  “Xác nhận phòng trống” trên dashboard và xác nhận.
- Click vùng trống trong Simulator để focus bàn phím. Giữ A, giữ thêm B,
  nhả A rồi nhả B (mỗi bước khoảng 0,2–0,5 giây): số người tăng 1 và quạt bật.
- Giữ B, giữ thêm A, nhả B rồi nhả A: số người giảm 1. Quạt chỉ tắt sau
  15 giây nếu không còn người. Chỉ nhấn A rồi nhả không được tăng số người.
- [Hướng dẫn hai tia và giới hạn đếm](people-counter.md). Hai nút nhấn là
  mô phỏng tín hiệu, không phải cảm biến hồng ngoại thật trong Wokwi.
- Bấm DHT22, đổi nhiệt độ lên 35°C. Twin báo HIGH_TEMPERATURE, health_score=10.
- Đưa nhiệt độ về 26°C; Alarm được cleared và twin phục hồi.
- Dừng Wokwi hơn 20 giây; twin chuyển OFFLINE và khóa các nút điều khiển.

## Cài trên Ubuntu mới

Cài Docker Engine và Docker Compose v2, ví dụ trên Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 python3
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Đăng nhập SSH lại để nhận group docker. Upload project vào
`/opt/classroom-digital-twin`. Sau đó:

```bash
cd /opt/classroom-digital-twin
python3 deployment/init-env.py --host YOUR_SERVER_IP
sh deployment/start.sh
```

Script tạo database schema khi trống, khởi động ThingsBoard và bootstrap mô
hình lớp học. Mật khẩu sinh ngẫu nhiên nằm trong `deployment/.env`.
Mở Security Group TCP80 cho dashboard và TCP1883 cho kết nối MQTT từ Wokwi.
Không cần Docker trên laptop khi server AWS đã chạy.

## Thêm vào ThingsBoard có sẵn

Điền `deployment/.env` với tài khoản SYS_ADMIN hợp lệ, tenant lớp học và
endpoint MQTT. Chạy trên cùng host Linux:

```bash
sh deployment/bootstrap-existing.sh
```

Trên Windows có thể đóng gói/upload/cập nhật endpoint bằng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\deploy-aws.ps1 -Server YOUR_SERVER_IP -KeyPath '..\produce-warehouse-digital-twin\iot_lab.pem' -Mode Existing
```

`-Mode Standalone` dành cho server mới đã cài Docker. Nếu IP EC2 đổi sau khi
stop/start, triển khai với IP mới rồi rebuild và restart Wokwi. Để giữ cố định
địa chỉ, có thể cấu hình Elastic IP riêng trong AWS.

## Khôi phục đủ dữ liệu cũ

Cần giữ: source project, `deployment/.env`, `.env.local`, `firmware/secrets.h`,
`firmware/.pio/build/esp32dev/firmware.bin`/`firmware.elf`, và bản dump PostgreSQL.
Các JSON trong `thingsboard/exports` giúp đối chiếu entity/dashboard, nhưng
không thay thế database dump khi muốn giữ tài khoản, token và lịch sử.
Giữ khóa SSH `iot_lab.pem` riêng nếu còn dùng EC2 hiện tại; khóa không được
đưa vào source hoặc Docker image. EC2 mới có thể dùng một key pair mới.

Dump khi server đang chạy:

```bash
cd /opt/produce-warehouse-digital-twin/deployment
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > classroom-server.sql.gz
```

Dump này bao gồm toàn bộ tenant trên ThingsBoard dùng chung. Phục hồi trên
database trống ở server mới: khởi động riêng PostgreSQL, nhập dump trước khi
khởi động ThingsBoard. Không chạy bước install schema trước khi nhập dump.

```bash
cd /opt/classroom-digital-twin/deployment
docker compose up -d --wait postgres
gzip -dc /path/to/classroom-server.sql.gz | docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose up -d thingsboard-ce
```

Sau phục hồi, cập nhật IP public/MQTT trong `.env`, chạy lại bootstrap và
đồng bộ secrets về laptop. Giữ tên project/volume cố định; không dùng
`docker compose down -v` nếu muốn giữ database.

## Kiểm tra dự án

```powershell
node .\tests\rules.test.cjs
node .\tests\lighting.test.cjs
python .\tests\wiring_test.py
python .\tests\live_rpc.py
```

`live_rpc.py` cần Wokwi đang online. Nó kiểm tra 4 kênh đèn và quạt, xác nhận
telemetry, rồi trả đầu ra về trạng thái ban đầu. Báo cáo tại `tests/results`.
Script yêu cầu đúng firmware version trong `config.h`, kiểm tra GPIO trả
về và chạy kiểm tra sơ đồ trước. Đây không phải cảm biến quang xác nhận
LED thực sự sáng; vẫn cần quan sát LED trong Wokwi.

Kiểm tra ảnh/dashboard dùng Chrome riêng và Playwright:

```powershell
python -m pip install --target tools/.runtime playwright paho-mqtt
python .\tools\capture-dashboard.py
python .\tests\aws_pipeline.py
```

`aws_pipeline.py` dùng các entity QA tạm và tự dọn sau khi kết thúc; không
publish dữ liệu giả vào Device Wokwi chính. Nó kiểm tra ảnh 4 vùng, quạt,
WebSocket, HIGH_TEMPERATURE, recovery và CONNECTION_LOST trên server thật.

Tài liệu chính thức: [Wokwi VS Code](https://docs.wokwi.com/vscode/getting-started),
[MQTT RPC](https://thingsboard.io/docs/reference/mqtt-api/),
[Widget development](https://thingsboard.io/docs/user-guide/contribution/widgets-development/).
