from patreon_mega_audit.mappings import load_mappings, save_mappings
from patreon_mega_audit.mega import MegaFolder
from patreon_mega_audit.patreon import PatreonPost
from patreon_mega_audit.report import build_report
from patreon_mega_audit.update_posts import load_replacements
import json


def test_manual_mapping_overrides_title_and_survives_renewal(tmp_path):
    path = tmp_path / "mappings.json"
    save_mappings(path, {"1": "Chosen folder"})
    post = PatreonPost("1", "Other folder", "https://mega.nz/folder/old#key", "today", None)
    folders = [MegaFolder("Other folder", "https://mega.nz/folder/wrong#key"), MegaFolder("Chosen folder", "https://mega.nz/folder/current#key")]
    report = build_report([post], folders, load_mappings(path))
    assert report.posts_with_mega_links[0].replacement_candidates[0].new_listing_url == folders[1].url


def test_missing_manual_folder_does_not_fall_back_to_title():
    post = PatreonPost("1", "Auto", "https://mega.nz/folder/old#key", "today", None)
    finding = build_report([post], [MegaFolder("Auto", "https://mega.nz/folder/new#key")], {"1": "Missing"}).posts_with_mega_links[0]
    assert finding.replacement_candidates == []
    assert "missing" in finding.update_status


def test_multiple_links_blocked_even_with_manual_mapping(tmp_path):
    post = PatreonPost("1", "Post", "https://mega.nz/folder/old#key https://mega.nz/folder/other#key", "today", None)
    finding = build_report([post], [MegaFolder("Folder", "https://mega.nz/folder/new#key")], {"1": "Folder"}).posts_with_mega_links[0]
    assert not finding.replacement_candidates
    assert finding.update_status == "Multiple links — manual editing required"
    # Older reports with candidates for multiple links are excluded too.
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"posts_with_mega_links": [{"referenced_folders": ["one", "two"], "replacement_candidates": [{}]}]}))
    assert load_replacements(path) == []


def test_duplicate_occurrences_of_same_link_are_supported():
    link = "https://mega.nz/folder/old#key"
    post = PatreonPost("1", "Folder", f'<a href="{link}">{link}</a>', "today", None)
    finding = build_report([post], [MegaFolder("Folder", "https://mega.nz/folder/new#key")]).posts_with_mega_links[0]
    assert len(finding.replacement_candidates) == 1


def test_duplicate_leaf_names_require_manual_path_selection():
    post = PatreonPost("1", "Alina", "https://mega.nz/folder/old#key", "today", None)
    folders = [MegaFolder("2024/Alina", "https://mega.nz/folder/a#key"), MegaFolder("2025/Alina", "https://mega.nz/folder/b#key")]
    assert not build_report([post], folders).posts_with_mega_links[0].replacement_candidates
    candidate = build_report([post], folders, {"1": "2025/Alina"}).posts_with_mega_links[0].replacement_candidates[0]
    assert candidate.new_listing_url == folders[1].url
