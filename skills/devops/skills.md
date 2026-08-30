---
name: devops
description: Best practices for CI/CD, Docker, and Infrastructure as Code.
license: MIT
---

# DevOps & CI/CD Skill

## Docker & Containerization
- Luôn sử dụng **Multi-stage builds** để giảm kích thước Docker image cuối cùng. Image chỉ chứa binary/build artifact và những dependencies cần thiết để chạy.
- Tránh chạy container bằng user `root`. Luôn tạo và sử dụng một non-root user (ví dụ: `appuser`) bên trong Dockerfile.
- Tối ưu hóa bộ nhớ đệm (Layer caching) bằng cách copy file chứa danh sách dependencies (`package.json`, `go.mod`, `requirements.txt`) và cài đặt trước khi copy toàn bộ mã nguồn.
- Chỉ sử dụng các base image chính thống, nên ghim tag phiên bản thay vì dùng `latest` (ví dụ: `node:20-alpine` thay vì `node:alpine`).

## CI/CD Pipelines (GitHub Actions / GitLab CI)
- Chia nhỏ pipeline thành các jobs độc lập và chạy song song khi có thể (ví dụ: `lint`, `test`, `build`).
- Không bao giờ hardcode credentials/secrets trong script. Sử dụng Secret Managers hoặc Repository Secrets.
- Thiết lập nguyên tắc Fail Fast (dừng CI ngay lập tức khi job Test/Lint thất bại).
- Tận dụng Caching cho các bước tốn thời gian như download dependencies (npm, maven, go modules).

## Infrastructure & Scripts
- Nếu viết bash script, luôn có cờ an toàn ở đầu script: `set -euo pipefail`.
- Tránh các lệnh thực thi không thể tái tạo (idempotent). Scripts nên có thể chạy nhiều lần mà không làm hỏng trạng thái hệ thống.
- Sử dụng các định dạng khai báo chuẩn (như Terraform, Kubernetes YAML, hoặc Docker Compose) thay vì tạo thủ công qua UI hay CLI.

## Output
- Cung cấp file cấu hình hợp lệ (YAML, JSON, Dockerfile).
- Không giải thích dòng lệnh quá dài dòng, trả về code trực tiếp.
