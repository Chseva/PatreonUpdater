from pathlib import Path

from patreon_mega_audit.mega import extract_mega_urls, normalize_folder_url, read_listing, title_matches_folder


def test_extracts_html_encoded_url_and_trailing_punctuation() -> None:
    content = '<p>Download: https://mega.nz/folder/abc123#key_456.</p>'
    assert extract_mega_urls(content) == ["https://mega.nz/folder/abc123#key_456"]


def test_normalizes_www_and_rejects_missing_key() -> None:
    assert normalize_folder_url("https://www.mega.nz/folder/abc#key") == "https://mega.nz/folder/abc#key"
    assert normalize_folder_url("https://mega.nz/folder/abc") is None


def test_reads_listing(tmp_path: Path) -> None:
    listing = tmp_path / "links.txt"
    listing.write_text("Alice (folder, shared as exported permanent folder link: https://mega.nz/folder/abc#key)\n", encoding="utf-8")
    assert read_listing(listing)[0].name == "Alice"


def test_title_folder_matching_uses_whole_words() -> None:
    assert title_matches_folder("【Look】 Alina (Tifa version)", "Alina")
    assert not title_matches_folder("【Look】 Katrinia", "Tina")


def test_recursive_listing_matches_leaf_and_preserves_paths(tmp_path):
    listing = tmp_path / "recursive.txt"
    listing.write_text(
        "2025/Alina (folder, shared as exported permanent folder link: https://mega.nz/folder/abc#key)\n"
        "2025/Alina/example.var (10 MB, shared as exported permanent file link: https://mega.nz/file/file#key)\n",
        encoding="utf-8",
    )
    folders = read_listing(listing)
    assert len(folders) == 1
    assert folders[0].name == "2025/Alina"
    assert title_matches_folder("【Look】 Alina", folders[0].name)
    assert title_matches_folder("【Look】 Alina", "/Patreon/VAM Looks/2025/Alina/")
    assert title_matches_folder("【Look】 Alina", "2025\\Alina")
    assert not title_matches_folder("2025 collection", folders[0].name)
    assert not title_matches_folder("【Look】 Katrinia", "2025/Tina")
