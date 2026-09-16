"""MEGA link extraction, normalization, and local-list parsing."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://(?:www\.)?mega\.nz/[^\s<>'\"`]+", re.IGNORECASE)
FOLDER_RE = re.compile(r"^/folder/([^/#?]+)#([^/?#]+)$", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}>\"'"


@dataclass(frozen=True)
class MegaFolder:
    """A locally listed MEGA folder."""

    name: str
    url: str


def title_matches_folder(title: str, folder_name: str) -> bool:
    """Match a listing label within a post title without matching partial words.

    Patreon titles often contain a category prefix (for example ``【Look】``)
    and a version suffix. Folder labels are usually the character/model name.
    This deliberately uses whole-word matching, so ``Tina`` does not match
    ``Katrinia``.
    """
    def words(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).casefold()
        return " ".join(re.findall(r"[a-z0-9]+", normalized))

    # Recursive MEGAcmd exports contain relative or absolute folder paths.
    # Preserve those paths as mapping identities, but match only the leaf name.
    leaf_name = folder_name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    candidate = words(leaf_name)
    title_words = words(title)
    return bool(candidate and re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", title_words))


def clean_url(value: str) -> str:
    """Decode HTML escaping and remove punctuation commonly wrapping URLs."""
    return html.unescape(value).strip().rstrip(TRAILING_PUNCTUATION)


def normalize_folder_url(value: str) -> str | None:
    """Return the canonical folder URL, or None if it is not a valid folder link."""
    url = clean_url(value)
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or parsed.netloc.lower() not in {"mega.nz", "www.mega.nz"}:
        return None
    match = FOLDER_RE.fullmatch(parsed.path + ("#" + parsed.fragment if parsed.fragment else ""))
    if not match:
        return None
    folder_id, key = match.groups()
    return f"https://mega.nz/folder/{folder_id}#{key}"


def extract_mega_urls(content: str | None) -> list[str]:
    """Extract distinct MEGA URLs in source order from HTML or plain post content."""
    if not content:
        return []
    found: list[str] = []
    for match in URL_RE.finditer(html.unescape(content)):
        url = clean_url(match.group(0))
        if url not in found:
            found.append(url)
    return found


def read_listing(path: Path) -> list[MegaFolder]:
    """Read each valid MEGA folder link and the text preceding it as its label."""
    folders: list[MegaFolder] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        urls = extract_mega_urls(raw_line)
        for url in urls:
            normalized = normalize_folder_url(url)
            if normalized is None:
                continue
            label = raw_line.split(url, 1)[0].rstrip(" (:-").strip()
            # The supplied export format is: "Name (folder, shared as ...:
            # https://mega.nz/folder/...)". Keep only the durable folder name,
            # which is what should be compared with a Patreon post title.
            label = re.split(r"\s*\(folder\s*,", label, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            folders.append(MegaFolder(name=label or f"Line {line_number}", url=normalized))
    return folders
