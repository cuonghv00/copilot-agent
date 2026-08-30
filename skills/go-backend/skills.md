---
name: go-backend
description: Best practices and idioms for Golang backend development.
license: MIT
---

# Go Backend Skill

## Quy ước Code (Idiomatic Go)
- Mã nguồn luôn tuân theo chuẩn format của `gofmt` hoặc `goimports`.
- Khai báo tên biến ngắn gọn trong scope nhỏ (ví dụ `c`, `req`, `err`), và dùng tên rõ ràng, có ý nghĩa cho biến ở cấp package hoặc struct fields.
- Tên Package nên là danh từ ngắn, viết thường, không có dấu gạch dưới hay pha trộn kiểu (camelCase) (ví dụ: `http`, `router`, không phải `http_router` hay `httpRouter`).
- Không lạm dụng `panic`. Sử dụng trả về nhiều giá trị `(result, err)` và xử lý lỗi một cách tường minh (`if err != nil`).

## Error Handling
- Bọc lỗi (Error Wrapping) sử dụng `fmt.Errorf("failed to do X: %w", err)` để duy trì context thay vì chỉ trả về `err` gốc.
- Đối với HTTP Server, luôn log chi tiết lỗi ở backend nhưng chỉ trả về mã lỗi chung chung (ví dụ 500) hoặc message thân thiện cho user (tránh rò rỉ thông tin hệ thống).

## Cấu trúc Concurrency
- Ưu tiên sử dụng Channels để chia sẻ dữ liệu giữa các Goroutine thay vì dùng Mutex lock trên bộ nhớ dùng chung ("Share memory by communicating, don't communicate by sharing memory").
- Khi chạy Goroutines, luôn có cơ chế kiểm soát vòng đời bằng `context.Context` hoặc `sync.WaitGroup` để tránh tình trạng goroutine rò rỉ (leak).
- Hàm luôn nhận `ctx context.Context` làm tham số đầu tiên nếu có bất kỳ tác vụ I/O, Network, hay Database nào.

## Kiến trúc & Testing
- Chia mã nguồn theo Domain/Tính năng hoặc theo Layer (Clean Architecture).
- Dependency Injection (Truyền các interface như Database, Cache) vào Struct thay vì sử dụng Global Variables (`var db *sql.DB`).
- Mọi logic phức tạp phải có Test (Table-driven tests) bằng package `testing`.

## Output
- Viết code sạch sẽ, không sinh ra code rác.
- Chỉ in nội dung file bị thay đổi.
