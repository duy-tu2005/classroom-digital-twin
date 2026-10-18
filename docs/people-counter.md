# Đếm người vào–ra bằng hai tia A/B

## Trên ThingsBoard có gì?

ThingsBoard nhận số đếm do ESP32 tính, lưu lịch sử trên Device và Asset,
hiển thị dashboard. Nó không chứa cảm biến vật lý. Wokwi hiện dùng **hai
nút nhấn A/B giả lập hai đầu ra số** thay cho PIR; không dùng cảm biến
thu remote IR để đếm người.

Mạch thật cần **2 bộ hồng ngoại cắt tia**, mỗi bộ gồm đầu phát và đầu thu:
tổng cộng 4 đầu, cho 2 tín hiệu A và B. Đặt hai tia nối tiếp theo chiều đi
qua cửa, A phía ngoài, B phía trong; mỗi tia cắt ngang lối đi.

```text
ngoài phòng →  tia A  →  tia B  → trong phòng
               GPIO13    GPIO27
```

Tia phải bố trí đủ gần để thân một người có thể chắn cả hai cùng lúc. Thuật
toán hiện yêu cầu đoạn chồng tia này; không coi hai lần nhấn rời rạc là một
lượt. Thiết kế dành cho một cửa, từng người qua, không đi song song/chen nhau.

## Chân và mức điện

| Tín hiệu | GPIO | Nút mô phỏng Wokwi |
|---|---:|---|
| A ngoài cửa | 13 (`D13`) | `gateA:1.r`, phím A |
| B trong cửa | 27 (`D27`) | `gateB:1.r`, phím B |
| GND | GND ESP32 | `gateA:2.l` và `gateB:2.l` |

Firmware dùng `INPUT_PULLUP`: LOW = chắn tia, HIGH = thông. Với cảm biến
thật, chọn đầu ra tương thích 3,3V/open-collector phù hợp và kiểm tra datasheet.
Không đưa 5V/12V/24V vào GPIO ESP32. Cảm biến công nghiệp cần mạch ghép mức
hoặc cách ly được thiết kế đúng; nguồn cảm biến không đồng nghĩa mức tín hiệu
GPIO. Hai nút hiện tại chỉ nối xuống GND, không cần dây nguồn riêng.

Đấu nút theo hai tiếp điểm **1 và 2**, không nối cả GPIO và GND vào hai chân
cùng tiếp điểm. Theo [tài liệu nút nhấn Wokwi](https://docs.wokwi.com/parts/wokwi-pushbutton),
hai chân 1.l/1.r luôn thông nhau; 2.l/2.r cũng vậy.

## Thuật toán thực sự chạy ở đâu?

- `firmware/people-counter.h`: máy trạng thái C++ dùng chung giữa firmware và unit test.
- `firmware/sketch.ino`: task lấy mẫu hai GPIO, lưu snapshot NVS, gửi MQTT và điều khiển quạt.
- `thingsboard/setup.py`: khai báo telemetry, PeopleCounter Entity View, widget và biểu đồ.
- `thingsboard/widgets/classroom.*`: số người, tổng vào/ra, hai tia, hiệu chuẩn.
- `thingsboard/rule-scripts/build-twin-payload.js`: chuyển dữ liệu đã xử lý sang Asset.

| Chuỗi ổn định | Kết quả |
|---|---|
| thông → A → AB → B → thông | Vào: +1 người, +1 lượt vào |
| thông → B → AB → A → thông | Ra: −1 người, +1 lượt ra |
| thông → A → thông hoặc B → thông | Không đếm |
| thông → A → AB → A → thông | Quay đầu, không đếm |
| Bắt đầu với AB hoặc bỏ qua đoạn AB | Không đoán chiều; báo cần hiệu chuẩn |
| Chuỗi kéo dài quá 8 giây | Bỏ lượt, đợi cả hai tia thông; báo cần hiệu chuẩn |
| Có lượt ra lúc số đếm bằng 0 | Giữ 0, vẫn tăng lượt ra, ghi lỗi/cần hiệu chuẩn |

Debounce 30 ms; cần hoàn tất và nhả cả hai tia mới chốt lượt. Mỗi lần lỗi
không lặp tăng liên tục khi tia vẫn bị giữ. Task lấy mẫu chạy riêng, tránh
bỏ toàn bộ chuỗi khi vòng MQTT đang kết nối lại. Telemetry gửi mỗi 5 giây
và ngay khi đổi tia, số đếm, đầu ra quạt hoặc xử lý RPC.

`counter_state`: IDLE, ENTERING, EXITING, BLOCKED. BLOCKED còn dùng cho chuỗi
không hợp lệ đang đợi thông cửa, không tự chứng minh có vật cản thật.
`counter_errors` và `counter_needs_calibration` là chẩn đoán; hiện chưa tạo
Alarm ThingsBoard riêng cho bộ đếm. Các Alarm nhiệt độ/Wi-Fi/cảm biến/đầu ra/
mất kết nối của dự án vẫn được giữ.

## Hiệu chuẩn, lưu số và giới hạn

Lần đầu, firmware đánh dấu số đếm chưa xác nhận. Chỉ bấm **Xác nhận phòng
trống** khi phòng thực sự không có người. Widget hỏi xác nhận và RPC
`resetPeopleCounter({confirmEmpty:true})` chỉ được firmware chấp nhận khi
hai tia thông và không có lượt đang xử lý. Nó đặt người, lượt vào/ra và lỗi
về 0; không xóa lịch sử ThingsBoard.

Snapshot lưu trong NVS của ESP32, không trong biến RAM đơn thuần. Trên
Wokwi, dữ liệu flash có thể phụ thuộc cách restart/reset mô phỏng; luôn
kiểm tra trạng thái hiệu chuẩn khi bắt đầu demo. Máy chủ lưu số lần cuối
nhưng **không tự ghi đè số đếm của ESP32**. Khôi phục server không đồng nghĩa
khôi phục bộ nhớ NVS của thiết bị.

AUTO bật quạt khi occupancy >0. Sau lượt ra cuối giữ 15 giây rồi tắt;
MANUAL vẫn độc lập. Hiệu chuẩn phòng trống hủy thời gian giữ, nên AUTO tắt.
Đèn vẫn điều khiển độc lập, không tự tắt theo số người.

Đếm hai tia là ước tính có điều kiện, không đảm bảo tuyệt đối: hai người
đi sát/sóng đôi, có cửa khác, mất nguồn giữa lượt, sai vị trí tia, phản xạ
hoặc che tia có thể làm lệch. Cần lối qua từng người và đối chiếu/hiệu chuẩn
định kỳ. Khi ngoại tuyến dashboard ghi rõ số cuối nhận, không giả thành 0.

## Thử trong Wokwi

1. Build, dừng mô phỏng cũ, Start Simulator. Kiểm tra `[BOOT] Classroom 2.0.1`.
2. Click vùng sơ đồ để bàn phím focus. Các phím A/B chỉ tác dụng trong Simulator.
3. Phòng trống: xác nhận trên dashboard. Không giữ tia trong khi hiệu chuẩn.
4. Vào: giữ A → giữ thêm B → nhả A → nhả B. Mỗi bước 0,2–0,5 giây.
5. Ra: giữ B → giữ thêm A → nhả B → nhả A.
6. Terminal phải có `[COUNT] IN` / `[COUNT] OUT`; ThingsBoard cập nhật số người.
7. Thử quay đầu A → AB → A → thông: không được tăng người.

Không thêm RPC “giả người vào/ra” cho Device thật: số người phải đến từ
đầu vào A/B, không từ nút dashboard tăng/giảm tùy ý.

Unit test thuật toán (Linux có g++):

```bash
g++ -std=c++11 -Wall -Wextra -Werror -fsanitize=address,undefined tests/people-counter.test.cpp -o /tmp/classroom-counter-test
/tmp/classroom-counter-test
```

Pipeline QA MQTT trên AWS là bài kiểm tra riêng cho giao diện và lưu dữ
liệu, không được coi là bằng chứng cảm biến vật lý hay Wokwi đã chạy.
