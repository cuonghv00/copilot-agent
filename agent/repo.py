import subprocess
import zipfile
import time
from pathlib import Path

def zip_repo(repo_path: Path, output_zip: Path, sync_command: str = None, sync_delay: int = 0) -> Path:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", "HEAD", "-o", str(output_zip)],
        cwd=repo_path, check=False, capture_output=True
    )
    if sync_command:
        cmd = sync_command.replace("{sync_dir}", str(output_zip.parent)).replace("{zip_path}", str(output_zip))
        subprocess.run(cmd, shell=True)
    
    if sync_delay > 0:
        time.sleep(sync_delay)
        
    return output_zip

def apply_downloaded_zip(zip_path: Path, repo_path: Path) -> list[str]:
    applied = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            target = repo_path / member
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            applied.append(member)
    zip_path.unlink(missing_ok=True)
    return applied

def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode == 0, result.stdout + result.stderr
