import shlex
import subprocess
import zipfile
import time
from pathlib import Path

_DEFAULT_EXCLUDE = {".git", "__pycache__", "node_modules", ".venv"}


def zip_repo(
    repo_path: Path,
    output_zip: Path,
    sync_command: str = None,
    sync_delay: int = 0,
    exclude_dirs: list[str] = None,
) -> Path:
    """
    Zip toàn bộ working tree (bao gồm cả unstaged changes) bằng cách walk
    filesystem trực tiếp — không dùng git archive để không bỏ sót file chưa commit.

    sync_command được thực thi với shell=True vì có thể chứa pipe/redirect.
    Đây là lệnh do người dùng tự cấu hình trong config.json nên được tin tưởng.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    _exclude = set(exclude_dirs) if exclude_dirs is not None else _DEFAULT_EXCLUDE

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(repo_path.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(repo_path)
            # Bỏ qua thư mục bị loại trừ
            if any(part in _exclude for part in rel.parts):
                continue
            zf.write(file_path, rel)

    if sync_command:
        # sync_command do user cấu hình, có thể chứa pipe/redirect → shell=True
        cmd = (
            sync_command
            .replace("{sync_dir}", str(output_zip.parent))
            .replace("{zip_path}", str(output_zip))
            .replace("{zip_filename}", output_zip.name)
        )
        subprocess.run(cmd, shell=True, check=False)

    if sync_delay > 0:
        time.sleep(sync_delay)

    return output_zip


def apply_downloaded_zip(zip_path: Path, repo_path: Path) -> list[str]:
    """
    Giải nén ZIP nhận từ Copilot vào repo_path.
    Bảo vệ path traversal: bỏ qua bất kỳ member nào trỏ ra ngoài repo_path.
    """
    repo_resolved = repo_path.resolve()
    applied = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            target = (repo_path / member).resolve()
            # Block path traversal (e.g., "../../.bashrc")
            try:
                target.relative_to(repo_resolved)
            except ValueError:
                continue  # Nằm ngoài repo_path — bỏ qua
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            applied.append(member)
    zip_path.unlink(missing_ok=True)
    return applied


def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    """
    Chạy verify command. Dùng shlex.split + shell=False để tránh shell injection.
    Lưu ý: command không được chứa pipe/redirect (dùng script wrapper nếu cần).
    """
    try:
        args = shlex.split(command)
    except ValueError as e:
        return False, f"Invalid command syntax: {e}"
    result = subprocess.run(
        args, shell=False, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode == 0, result.stdout + result.stderr
