# Python Backend Skill

## Quy ước code
- Dùng type hints cho tất cả functions
- Docstring theo Google style
- Tên biến/function theo snake_case
- Tối đa 100 ký tự mỗi dòng

## Testing
- Viết unit test cho mỗi function mới
- Dùng pytest, không dùng unittest
- Mock external calls (HTTP, DB, file I/O)

## Error handling
- Không dùng bare `except:`
- Log lỗi trước khi raise
- Custom exception classes nếu cần

## Output
- Không hiện thị source code trong kết quả.
- Chỉ hiển thị tóm tắt và link file có thể download.
