import re
from pathlib import Path

_PLACEHOLDER_URLS = {'', 'https://example.com/workspace.zip'}

OUTPUT_RULES_TEMPLATE = """\n─── QUY ĐỊNH KẾT QUẢ ───
Sau khi hoàn thành, hãy:
1. Tóm tắt ngắn các thay đổi đã thực hiện
2. Liệt kê bảng các file thay đổi: tên file | đường dẫn | mô tả ngắn
3. Xuất file nén (.zip) chứa toàn bộ mã nguồn với cấu trúc thư mục giữ nguyên, kèm nút Download
4. Liệt kê các lệnh để verify kết quả"""

OUTPUT_RULES_SHORT = "\nVui lòng xuất lại file zip cập nhật và cung cấp nút Download."

def load_skill_content(prompt: str, skills_dir: Path) -> str:
    mentions = re.findall(r'@([\w-]+)', prompt)
    parts = []
    for name in mentions:
        skill_file = skills_dir / name / "skills.md"
        if skill_file.exists():
            content = skill_file.read_text().strip()
            non_comment = "\n".join(
                l for l in content.splitlines()
                if l.strip() and not l.strip().startswith("<!--")
            )
            if non_comment:
                parts.append(content)
    return "\n\n".join(parts)

def build_full_prompt(
    user_prompt: str,
    onedrive_link: str,
    skill_content: str,
    request_output: bool,
    is_new_session: bool,
) -> str:
    parts: list[str] = []

    link = (onedrive_link or "").strip()
    if link and link not in _PLACEHOLDER_URLS:
        parts.append(f"📎 Mã nguồn dự án: {link}")
        parts.append("")

    parts.append(user_prompt)

    if skill_content:
        parts.append("")
        parts.append(skill_content)

    if request_output:
        parts.append(OUTPUT_RULES_TEMPLATE)

    return "\n".join(parts)
