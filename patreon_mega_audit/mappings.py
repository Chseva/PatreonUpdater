"""Local post-ID to folder-name mappings, retained across link renewal."""
import json
from pathlib import Path


def load_mappings(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ValueError("Invalid manual mappings file.")
    return value


def save_mappings(path: Path, mappings: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(mappings, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
