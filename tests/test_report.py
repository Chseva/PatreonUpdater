from patreon_mega_audit.mega import MegaFolder
from patreon_mega_audit.patreon import PatreonPost
from patreon_mega_audit.report import build_report


def test_classifies_match_stale_and_unreferenced() -> None:
    local = [
        MegaFolder("Alice", "https://mega.nz/folder/a#k"),
        MegaFolder("Bob", "https://mega.nz/folder/b#k"),
    ]
    posts = [PatreonPost("1", "Post", "https://mega.nz/folder/a#k https://mega.nz/folder/c#k", None, None)]
    report = build_report(posts, local)
    finding = report.posts_with_mega_links[0]
    assert finding.referenced_folders == ["https://mega.nz/folder/a#k"]
    assert finding.missing_or_stale_candidates == ["https://mega.nz/folder/c#k"]
    assert [folder.name for folder in report.unreferenced_local_folders] == ["Bob"]


def test_records_old_and_new_link_when_title_matches_folder() -> None:
    local = [MegaFolder("Alina", "https://mega.nz/folder/new#key")]
    posts = [PatreonPost("1", "【Look】 Alina (Tifa version)", "https://mega.nz/folder/old#key", "2026-01-01", None)]
    candidate = build_report(posts, local).posts_with_mega_links[0].replacement_candidates[0]
    assert candidate.folder_name == "Alina"
    assert candidate.old_post_url == "https://mega.nz/folder/old#key"
    assert candidate.new_listing_url == "https://mega.nz/folder/new#key"


def test_generates_id_based_post_and_edit_urls() -> None:
    post = PatreonPost("123456789", "Tina", "https://mega.nz/folder/old#key", "2026-01-01", "/legacy-url")
    finding = build_report([post], []).posts_with_mega_links[0]
    assert finding.post_url == "https://www.patreon.com/posts/123456789"
    assert finding.edit_url == "https://www.patreon.com/posts/123456789/edit"
