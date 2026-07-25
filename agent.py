#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
from pathlib import Path


def load_config():
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


if __name__ == "__main__":
    config = load_config()
    print(f"[CLI] Config loaded: WebSocket port {config['websocket_port']}")
