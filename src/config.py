import json
import random
from pathlib import Path


CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "GuobaPrincess"
CONFIG_FILE = CONFIG_DIR / "config.json"

_XIAOMI_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#F7DC6F", "#BB8FCE", "#85C1E9", "#F8C471",
    "#82E0AA", "#DDA0DD", "#FF8A65", "#4DB6AC",
]

_DEFAULTS = {
    "pos_x": None,
    "pos_y": None,
    "scale": 0.5,
    "notes": [],
    "pomodoro_work": 25,
    "pomodoro_break": 5,
    "show_clock": True,
    "snapping": True,
    "show_head": True,
    "character": "jiaoyi",
    "apps": [
        {"name": "计算器", "cmd": "calc"},
        {"name": "记事本", "cmd": "notepad"},
        {"name": "画图", "cmd": "mspaint"},
        {"name": "文件管理器", "cmd": "explorer"},
    ],
}


class Config:
    def __init__(self):
        self._data = dict(_DEFAULTS)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except Exception:
                pass
        # migrate old string-only notes
        notes = self._data.get("notes", [])
        if notes and isinstance(notes[0], str):
            self._data["notes"] = [
                {"text": t, "color": random.choice(_XIAOMI_COLORS)} for t in notes
            ]

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    # convenience helpers
    @property
    def notes(self) -> list:
        return self._data.get("notes", [])

    def add_note(self, text: str):
        notes = self._data.setdefault("notes", [])
        prev = notes[-1]["color"] if notes else None
        color = random.choice([c for c in _XIAOMI_COLORS if c != prev]) if prev else random.choice(_XIAOMI_COLORS)
        notes.append({"text": text, "color": color})

    def remove_note(self, index: int):
        notes = self._data.get("notes", [])
        if 0 <= index < len(notes):
            notes.pop(index)

    def update_note(self, index: int, text: str):
        notes = self._data.get("notes", [])
        if 0 <= index < len(notes):
            notes[index]["text"] = text

    def clear_notes(self):
        self._data["notes"] = []

    # apps helpers
    @property
    def apps(self) -> list:
        return self._data.get("apps", _DEFAULTS["apps"])

    def add_app(self, name: str, cmd: str):
        self._data.setdefault("apps", []).append({"name": name, "cmd": cmd})

    def remove_app(self, index: int):
        apps = self._data.get("apps", [])
        if 0 <= index < len(apps):
            apps.pop(index)

    def set_apps(self, apps: list):
        self._data["apps"] = list(apps)
