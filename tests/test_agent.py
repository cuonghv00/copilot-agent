import json
import os
import tempfile
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_load_config():
    """load_config returns a dict with expected keys."""
    from agent import load_config
    config = load_config()
    assert isinstance(config, dict)
    assert "repo_path" in config
    assert "websocket_port" in config
    assert config["websocket_port"] == 8765

def test_zip_repo_creates_zip():
    """zip_repo creates a valid zip file from a directory."""
    from agent import zip_repo
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake repo
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("print('hello')")
        (repo / "utils.py").write_text("def add(a, b): return a + b")
        sub = repo / "src"
        sub.mkdir()
        (sub / "core.py").write_text("# core module")

        output = Path(tmpdir) / "output"
        output.mkdir()

        result = zip_repo(repo, output / "workspace.zip", [])
        assert result.exists()
        assert result.name == "workspace.zip"

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "main.py" in names
            assert "utils.py" in names
            assert "src/core.py" in names

def test_zip_repo_excludes_dirs():
    """zip_repo skips directories listed in exclude_dirs."""
    from agent import zip_repo
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        (repo / "app.py").write_text("# app")
        git_dir = repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("# git config")
        cache_dir = repo / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "app.cpython-310.pyc").write_bytes(b"\x00")

        output = Path(tmpdir) / "output"
        output.mkdir()

        result = zip_repo(repo, output / "workspace.zip", [".git", "__pycache__"])
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "app.py" in names
            assert not any(".git" in n for n in names)
            assert not any("__pycache__" in n for n in names)
