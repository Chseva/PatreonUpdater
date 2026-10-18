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
    links: list["PostLink"]
    update_status: str = ""


@dataclass(frozen=True)
class PostLink:
    link_number: int
    url: str
    valid_folder_link: bool
    mapped_folder: str | None
    status: str


@dataclass(frozen=True)
class ReplacementCandidate:
    """A title-associated listing entry whose current URL differs from the post."""

    folder_name: str
    old_post_url: str
    new_listing_url: str
    link_number: int = 1


@dataclass(frozen=True)
class AuditReport:
    posts_with_mega_links: list[PostFinding]
    unreferenced_local_folders: list[MegaFolder]

    def as_dict(self) -> dict:
        return asdict(self)


def indexed_mega_links(content: str | None) -> list[tuple[str, str | None]]:
    """Return distinct MEGA URLs in content order with canonical folder URLs."""
    indexed: list[tuple[str, str | None]] = []
    seen_links: set[str] = set()
    for raw in extract_mega_urls(content):
        normalized = normalize_folder_url(raw)
        identity = normalized or raw
        if identity not in seen_links:
            seen_links.add(identity)
            indexed.append((identity, normalized))
    return indexed


def build_report(posts: list[PatreonPost], local_folders: list[MegaFolder], mappings: dict[str, str | dict[str, str]] | None = None) -> AuditReport:
    mappings = mappings or {}
    local_by_url = {folder.url: folder for folder in local_folders}
    referenced_urls: set[str] = set()
    findings: list[PostFinding] = []
    for post in posts:
        indexed = indexed_mega_links(post.content)
        extracted = [raw for raw, _ in indexed]
        valid = [normalized for _, normalized in indexed if normalized]
        invalid = [url for url, normalized in indexed if normalized is None]
        matched = list(dict.fromkeys(url for url in valid if url in local_by_url))
        stale = list(dict.fromkeys(url for url in valid if url not in local_by_url))
        replacements: list[ReplacementCandidate] = []
        status = ""
        stored = mappings.get(post.id)
        per_link = stored if isinstance(stored, dict) else {}
        legacy_folder = stored if isinstance(stored, str) and len(indexed) == 1 else None
        link_findings: list[PostLink] = []
        statuses: list[str] = []
        for link_number, (url, normalized) in enumerate(indexed, 1):
            if normalized is None:
                link_status = "Invalid link — manual editing required"
                mapped_name = None
            else:
                selected_name = per_link.get(str(link_number)) or legacy_folder
                manual = bool(selected_name)
                matching_folders = list(dict.fromkeys(
                    folder for folder in local_folders
                    if (folder.name == selected_name if manual else (len(indexed) == 1 and title_matches_folder(post.title, folder.name)))
                ))
                if len(matching_folders) == 1:
                    folder = matching_folders[0]
                    mapped_name = folder.name
                    link_status = "Manual mapping" if manual else "Title match"
                    if folder.url != normalized:
                        replacements.append(ReplacementCandidate(folder.name, normalized, folder.url, link_number))
                    else:
                        link_status = "Link already current"
                elif matching_folders:
                    mapped_name = selected_name
                    link_status = "Ambiguous folder name — choose a unique folder"
                elif manual:
                    mapped_name = selected_name
                    link_status = "Mapped folder missing from listing"
                else:
                    mapped_name = None
                    link_status = "Choose a folder for this link" if len(indexed) > 1 else "No folder match"
            link_findings.append(PostLink(link_number, url, normalized is not None, mapped_name, link_status))
            statuses.append(f"Link {link_number}: {link_status}")
        if len(indexed) > 1:
            status = "; ".join(statuses) if any(str(index) in per_link for index in range(1, len(indexed) + 1)) else "Multiple links — manual editing required"
        elif statuses:
            status = statuses[0].split(": ", 1)[-1]
        if extracted:
            referenced_urls.update(matched)
            # API-provided post URLs can be relative and may depend on a campaign
            # vanity name. The ID-based URLs are stable and suitable for direct
            # browser navigation in the later editing workflow.
            post_url = f"https://www.patreon.com/posts/{post.id}"
            edit_url = f"{post_url}/edit"
            findings.append(PostFinding(post.id, post.title, post_url, edit_url, post.published_at, matched, stale, invalid, replacements, link_findings, status))
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
                f"- Link {item.link_number} — {item.folder_name}: {item.old_post_url} → {item.new_listing_url}"
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

