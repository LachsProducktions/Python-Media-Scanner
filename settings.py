"""
settings.py - simple settings manager

Saves settings.json with defaults if not present.
"""
import json

DEFAULTS = {
    "tab_order": ["Videos","Music","Photos","Other"],
    "include_hash": False,
    "export_format": "txt",
    "last_scan_path": "",
    "compare_mode": "auto"
}

class SettingsManager:
    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path,"r",encoding="utf-8") as f:
                data = json.load(f)
            # ensure defaults
            for k,v in DEFAULTS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            # write defaults
            self.save(DEFAULTS.copy())
            return DEFAULTS.copy()

    def save(self, data):
        with open(self.path,"w",encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
