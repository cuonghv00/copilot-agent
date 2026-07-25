#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
import os
import subprocess
import zipfile
from pathlib import Path


def load_config():
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def zip_repo(repo_path: Path, output_zip: Path, exclude_dirs: list[str]) -> Path:
    """Zip all files in repo_path into output_zip, excluding specified directories.

    Args:
        repo_path: Path to the repository directory to zip.
        output_zip: Path where the zip file will be created.
        exclude_dirs: List of directory names to skip (e.g., ['.git', '__pycache__']).

    Returns:
        Path to the created zip file.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(repo_path)
                zipf.write(file_path, arcname)
    return output_zip


def extract_zip(zip_path: Path, target_dir: Path) -> bool:
    """Extract a zip file into target_dir and delete the zip afterwards.

    Args:
        zip_path: Path to the zip file to extract.
        target_dir: Directory to extract files into.

    Returns:
        True if extraction succeeded, False otherwise.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)
        zip_path.unlink()
        return True
    except (zipfile.BadZipFile, OSError) as e:
        print(f"[CLI] Extract error: {e}")
        return False


def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    """Run a shell command and return (success, combined_output).

    Args:
        command: Shell command string to execute.
        cwd: Working directory for the command.

    Returns:
        Tuple of (success: bool, output: str).
    """
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    combined = result.stdout + result.stderr
    return result.returncode == 0, combined


if __name__ == "__main__":
    config = load_config()
    print(f"[CLI] Config loaded: WebSocket port {config['websocket_port']}")
