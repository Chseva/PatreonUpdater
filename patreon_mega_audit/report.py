"""Build Markdown and JSON-safe audit reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .mega import MegaFolder, extract_mega_urls, normalize_folder_url, title_matches_folder
from .patreon import PatreonPost


@dataclass(frozen=True)
class PostFinding:
    post_id: str
    title: str
    post_url: str
    edit_url: str
    published_at: str | None
    referenced_folders: list[str]
    missing_or_stale_candidates: list[str]
    structurally_invalid_links: list[str]
    replacement_candidates: list["ReplacementCandidate"]
    update_status: str = ""


@dataclass(frozen=True)
class ReplacementCandidate:
    """A title-associated listing entry whose current URL differs from the post."""

    folder_name: str
    old_post_url: str
    new_listing_url: str


@dataclass(frozen=True)
class AuditReport:
    posts_with_mega_links: list[PostFinding]
    unreferenced_local_folders: list[MegaFolder]

    def as_dict(self) -> dict:
        return asdict(self)


def build_report(posts: list[PatreonPost], local_folders: list[MegaFolder], mappings: dict[str, str] | None = None) -> AuditReport:
    mappings = mappings or {}
    local_by_url = {folder.url: folder for folder in local_folders}
    referenced_urls: set[str] = set()
    findings: list[PostFinding] = []
    for post in posts:
        extracted = extract_mega_urls(post.content)
        valid = [normalized for raw in extracted if (normalized := normalize_folder_url(raw))]
        invalid = [raw for raw in extracted if normalize_folder_url(raw) is None]
        matched = list(dict.fromkeys(url for url in valid if url in local_by_url))
        stale = list(dict.fromkeys(url for url in valid if url not in local_by_url))
        replacements: list[ReplacementCandidate] = []
        distinct = set(valid + invalid)
        status = ""
        if len(distinct) > 1:
            status = "Multiple links — manual editing required"
        elif invalid:
            status = "Invalid link — manual editing required"
        elif valid:
            manual = post.id in mappings
            matching_folders = list(dict.fromkeys(
                folder for folder in local_folders
                if (folder.name == mappings[post.id] if manual else title_matches_folder(post.title, folder.name))
            ))
            if len(matching_folders) == 1:
                folder = matching_folders[0]
                status = "Manual mapping" if manual else "Title match"
                if folder.url != valid[0]:
                    replacements.append(ReplacementCandidate(folder.name, valid[0], folder.url))
            elif matching_folders:
                status = "Ambiguous folder name — choose a unique folder"
            elif manual:
                status = "Mapped folder missing from listing"
            else:
                status = "No folder match"
        if extracted:
            referenced_urls.update(matched)
            # API-provided post URLs can be relative and may depend on a campaign
            # vanity name. The ID-based URLs are stable and suitable for direct
            # browser navigation in the later editing workflow.
            post_url = f"https://www.patreon.com/posts/{post.id}"
            edit_url = f"{post_url}/edit"
            findings.append(PostFinding(post.id, post.title, post_url, edit_url, post.published_at, matched, stale, invalid, replacements, status))
    unreferenced = [folder for folder in local_folders if folder.url not in referenced_urls]
    return AuditReport(findings, unreferenced)


def render_markdown(report: AuditReport) -> str:
    lines = ["# Patreon MEGA Link Audit", "", f"Posts containing MEGA URLs: **{len(report.posts_with_mega_links)}**", ""]
    lines.extend(["## Posts containing MEGA links", ""])
    for finding in report.posts_with_mega_links:
        heading = f"### {finding.title} (ID {finding.post_id})"
        lines.extend([heading, ""])
        lines.extend([f"Post: {finding.post_url}", f"Edit: {finding.edit_url}", ""])
        lines.extend([f"Status: {finding.update_status}", ""])
        if finding.referenced_folders:
            lines.append("Referenced local folders:")
            lines.extend(f"- {url}" for url in finding.referenced_folders)
        if finding.missing_or_stale_candidates:
            lines.append("Missing/stale candidates (not in local listing):")
            lines.extend(f"- {url}" for url in finding.missing_or_stale_candidates)
        if finding.structurally_invalid_links:
            lines.append("Structurally invalid MEGA links:")
            lines.extend(f"- {url}" for url in finding.structurally_invalid_links)
        if finding.replacement_candidates:
            lines.append("Replacement candidates (old post link → new listing link):")
            lines.extend(
                f"- {item.folder_name}: {item.old_post_url} → {item.new_listing_url}"
                for item in finding.replacement_candidates
            )
        if not (finding.referenced_folders or finding.missing_or_stale_candidates or finding.structurally_invalid_links):
            lines.append("- No folder-form MEGA link found.")
        lines.append("")
    lines.extend(["## Local MEGA folders not referenced by any published post", ""])
    if report.unreferenced_local_folders:
        lines.extend(f"- {folder.name}: {folder.url}" for folder in report.unreferenced_local_folders)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)
