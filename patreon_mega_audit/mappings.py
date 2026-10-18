"""Local post/link-to-folder mappings, retained across link renewal."""
import json
from pathlib import Path


MappingValue = str | dict[str, str]


def load_mappings(path: Path) -> dict[str, MappingValue]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        not isinstance(k, str)
        or not (
            isinstance(v, str)
            or (isinstance(v, dict) and all(isinstance(index, str) and index.isdigit() and isinstance(name, str) for index, name in v.items()))
        )
        for k, v in value.items()
    ):
        raise ValueError("Invalid manual mappings file.")
    return value


def save_mappings(path: Path, mappings: dict[str, MappingValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(mappings, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)

