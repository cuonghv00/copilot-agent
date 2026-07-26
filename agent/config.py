import json
from datetime import datetime
from pathlib import Path

def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path) as f:
        return json.load(f)

class AgentState:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.last_session_id: str | None = None
        self.model: str = "auto"
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.last_session_id = data.get("last_session_id")
                self.model = data.get("model", "auto")
            except Exception:
                pass

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_session_id": self.last_session_id,
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
        }, indent=2))
