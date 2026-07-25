#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
import os
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


if __name__ == "__main__":
    config = load_config()
    print(f"[CLI] Config loaded: WebSocket port {config['websocket_port']}")
