"""Apply reviewed MEGA URL replacements in Patreon post editors with Playwright.

This module never retrieves Patreon content: it consumes the reviewed JSON audit
report produced by this project and navigates to its ID-derived edit URLs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    post_id: str
    title: str
    edit_url: str
    folder_name: str
    old_url: str
    new_url: str


def load_replacements(path: Path) -> list[Replacement]:
    """Load only title-matched, old-to-new mappings from an audit JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    replacements: list[Replacement] = []
    for post in payload.get("posts_with_mega_links", []):
        links = set(post.get("referenced_folders", []) + post.get("missing_or_stale_candidates", []) + post.get("structurally_invalid_links", []))
        if len(links) > 1 or post.get("structurally_invalid_links"):
            continue
        for item in post.get("replacement_candidates", []):
            replacements.append(
                Replacement(
                    post_id=str(post["post_id"]),
                    title=post["title"],
                    edit_url=post["edit_url"],
                    folder_name=item["folder_name"],
                    old_url=item["old_post_url"],
                    new_url=item["new_listing_url"],
                )
            )
    return replacements


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Apply reviewed Patreon MEGA-link replacements with Playwright.")
    result.add_argument("--report", type=Path, required=True, help="JSON report produced by patreon-mega-audit")
    selection = result.add_mutually_exclusive_group()
    selection.add_argument("--post-id", help="Apply candidates for this one Patreon post ID")
    selection.add_argument("--all", action="store_true", help="Select all candidates (requires --apply --confirm REPLACE-ALL)")
    result.add_argument("--apply", action="store_true", help="Actually save changes; otherwise only print a dry run")
    result.add_argument("--confirm", help="For --all, must be exactly REPLACE-ALL")
    result.add_argument("--profile-dir", type=Path, default=Path(".playwright-patreon-profile"), help="Persistent browser profile directory")
    result.add_argument("--link-text", default="Mega", help="Visible text of the MEGA link in the editor")
    result.add_argument("--editor-language", choices=["auto", "en", "zh"], default="auto")
    result.add_argument("--link-button-name", help="Override the editor link button label")
    result.add_argument("--url-field-name", help="Override the link URL field label")
    result.add_argument("--save-button-name", help="Override the link-dialog save label")
    result.add_argument("--update-button-name", help="Override the post update label")
    result.add_argument("--save-wait-seconds", type=int, default=5, help="Seconds to wait for Patreon to save before verification (minimum: 1)")
    result.add_argument("--auto-confirm", action="store_true", help="Skip terminal prompts after a GUI confirmation")
    return result


EDITOR_LABELS = {
    "en": {"link_button": ["Link", "Insert link"], "url_field": ["Link URL or email address", "Link URL or email"], "save_button": ["Save"], "update_button": ["Update"]},
    "zh": {"link_button": ["链接", "連結"], "url_field": ["链接网址或电子邮箱地址", "連結網址或電子郵件地址"], "save_button": ["保存", "儲存"], "update_button": ["更新"]},
}


def editor_control(page, role: str, control: str, args):
    override = getattr(args, control + "_name", None)
    language = getattr(args, "editor_language", "auto")
    languages = ["en", "zh"] if language == "auto" else [language]
    names = [override] if override else [name for lang in languages for name in EDITOR_LABELS[lang][control]]
    pattern = re.compile("^(?:" + "|".join(re.escape(name) for name in names) + ")$", re.IGNORECASE)
    locator = page.get_by_role(role, name=pattern)
    # Playwright strict matching rejects ambiguous controls rather than picking one.
    try:
        locator.wait_for(state="visible", timeout=10000)
    except Exception as error:
        raise RuntimeError(f"Could not identify the {control.replace('_', ' ')}. Check Settings → Patreon editor language. Supported labels: {', '.join(names)}") from error
    return locator


def apply_replacement(page, item: Replacement, args: argparse.Namespace) -> None:
    """Use the recorded editor interaction and require confirmation before submit."""
    page.goto(item.edit_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1_000)
    # These labels come from the user's Playwright codegen recording. They are
    # command-line options because Patreon localizes its editor UI.
    # Prefer the reviewed old URL itself over its visible text. Patreon may
    # render the same hyperlink with a localized or creator-chosen label.
    old_url_link = page.locator(f'a[href="{item.old_url}"]')
    if old_url_link.count() > 0:
        old_url_link.first.click()
    else:
        # Retain the recorded selector as a configurable fallback for editor
        # variants that do not expose the original URL in an href attribute.
        fallback = page.get_by_role("link", name=args.link_text, exact=True)
        if fallback.count() == 0:
            links = page.locator("a").evaluate_all(
                "elements => elements.slice(0, 25).map(a => ({text: (a.innerText || '').trim(), href: a.href}))"
            )
            raise RuntimeError(
                f"Post {item.post_id}: expected old URL was not found in the editor. "
                f"Current page: {page.url}. Visible links: {links!r}. No change saved."
            )
        fallback.click()
    editor_control(page, "button", "link_button", args).click()
    url_field = editor_control(page, "textbox", "url_field", args)
    url_field.wait_for(state="visible")
    actual_old_url = url_field.input_value()
    if actual_old_url != item.old_url:
        raise RuntimeError(
            f"Post {item.post_id}: editor URL differs from report; expected {item.old_url!r}, got {actual_old_url!r}. No change saved."
        )
    url_field.fill(item.new_url)
    editor_control(page, "button", "save_button", args).click()
    if not args.auto_confirm:
        confirmation = input(
            f"Replacement is prepared for post {item.post_id}. Review the visible browser, then type UPDATE to press Patreon's Update button (anything else cancels): "
        )
        if confirmation != "UPDATE":
            raise RuntimeError(f"Post {item.post_id}: update cancelled before submission.")
    editor_control(page, "button", "update_button", args).click()
    # Do not close the browser immediately after clicking Update: Patreon is a
    # single-page app and an in-flight save can otherwise be interrupted.
    page.wait_for_timeout(args.save_wait_seconds * 1_000)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1_500)
    saved_link = page.locator(f'a[href="{item.new_url}"]')
    if saved_link.count() == 0:
        raise RuntimeError(
            f"Post {item.post_id}: Patreon did not show the new URL after reloading. "
            "The browser remains open so you can inspect the editor; do not assume the update succeeded."
        )


def wait_for_login(page, timeout_seconds: int = 300) -> None:
    """Keep the visible browser open while a first-time user signs in."""
    deadline = time.monotonic() + timeout_seconds
    while "/login" in page.url:
        if time.monotonic() >= deadline:
            raise RuntimeError("Patreon login did not finish within five minutes. No updates were submitted.")
        page.wait_for_timeout(1_000)


def hold_error_open(error: Exception) -> None:
    """Keep an updater error visible in both console and windowed EXE builds."""
    message = f"Updater stopped: {error}\n\nNo further posts were updated."
    print(f"\n{message}")
    if sys.stdin is not None and sys.stdin.isatty():
        input("The browser has been left open for inspection. Press Enter here to close it after reviewing the page... ")
        return
    if getattr(sys, "frozen", False):
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Patreon Updater", message)
        root.destroy()


def main() -> int:
    args = parser().parse_args()
    if args.save_wait_seconds < 1:
        parser().error("--save-wait-seconds must be at least 1")
    if not args.report.is_file():
        parser().error(f"Report does not exist: {args.report}")
    candidates = load_replacements(args.report)
    if args.post_id:
        candidates = [item for item in candidates if item.post_id == args.post_id]
    elif not args.all:
        # Defaulting to a dry-run list prevents accidental write operations.
        args.apply = False
    if args.all and args.apply and args.confirm != "REPLACE-ALL":
        parser().error("Batch edits require --confirm REPLACE-ALL")
    if args.post_id and not candidates:
        parser().error(f"No replacement candidate found for post ID {args.post_id}")
    if not candidates:
        print("No replacement candidates found.")
        return 0
    for item in candidates:
        print(f"{item.post_id} | {item.title} | {item.folder_name}\n  OLD {item.old_url}\n  NEW {item.new_url}\n  EDIT {item.edit_url}")
    if not args.apply:
        print("\nDry run only. Nothing was changed. Use --post-id ID --apply after reviewing one mapping.")
        return 0
    try:
        if getattr(sys, "frozen", False):
            # Matches the browser location used by the PyInstaller build script.
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install -e .[browser] && python -m playwright install chromium")
        return 2
    args.profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(str(args.profile_dir), headless=False)
        page = browser.pages[0] if browser.pages else browser.new_page()
        try:
            page.goto("https://www.patreon.com/login", wait_until="domcontentloaded")
            if args.auto_confirm:
                wait_for_login(page)
            else:
                input("Log in to Patreon in the opened browser, then press Enter here to begin the reviewed update(s)... ")
            for item in candidates:
                apply_replacement(page, item, args)
                print(f"Verified updated post {item.post_id}: {item.old_url} -> {item.new_url}")
        except Exception as error:
            hold_error_open(error)
            return 1
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
