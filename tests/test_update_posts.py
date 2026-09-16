import json
from pathlib import Path

from patreon_mega_audit.update_posts import load_replacements


def test_loads_only_replacement_candidates(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"posts_with_mega_links": [{
        "post_id": "123456789", "title": "Tina", "edit_url": "https://www.patreon.com/posts/123456789/edit",
        "replacement_candidates": [{"folder_name": "Tina", "old_post_url": "old", "new_listing_url": "new"}],
    }]}), encoding="utf-8")
    assert load_replacements(report) == [
        load_replacements(report)[0]
    ]
    item = load_replacements(report)[0]
    assert (item.post_id, item.old_url, item.new_url) == ("123456789", "old", "new")
