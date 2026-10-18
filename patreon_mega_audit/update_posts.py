"""Apply reviewed MEGA URL replacements in Patreon post editors with Playwright.

This module never retrieves Patreon content: it consumes the reviewed JSON audit
report produced by this project and navigates to its ID-derived edit URLs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    post_id: str
    title: str
    edit_url: str
    folder_name: str
    old_url: str
    new_url: str
    link_number: int = 1


def load_replacements(path: Path) -> list[Replacement]:
    """Load only title-matched, old-to-new mappings from an audit JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    replacements: list[Replacement] = []
    for post in payload.get("posts_with_mega_links", []):
        links = set(post.get("referenced_folders", []) + post.get("missing_or_stale_candidates", []) + post.get("structurally_invalid_links", []))
        for item in post.get("replacement_candidates", []):
            # Old reports did not record which link a candidate belonged to.
            if (len(links) > 1 or post.get("structurally_invalid_links")) and "link_number" not in item:
                continue
            replacements.append(
                Replacement(
                    post_id=str(post["post_id"]),
                    title=post["title"],
                    edit_url=post["edit_url"],
                    folder_name=item["folder_name"],
                    old_url=item["old_post_url"],
                    new_url=item["new_listing_url"],
                    link_number=int(item.get("link_number", 1)),
                )
            )
    return replacements


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Apply reviewed Patreon MEGA-link replacements with Playwright.")
    result.add_argument("--report", type=Path, required=True, help="JSON report produced by patreon-mega-audit")
    selection = result.add_mutually_exclusive_group()
    selection.add_argument("--post-id", help="Apply candidates for this one Patreon post ID")
    result.add_argument("--link-number", type=int, help="With --post-id, select only this numbered MEGA link")
    selection.add_argument("--all", action="store_true", help="Select all candidates (requires --apply --confirm REPLACE-ALL)")
    result.add_argument("--apply", action="store_true", help="Actually save changes; otherwise only print a dry run")
    result.add_argument("--confirm", help="For --all, must be exactly REPLACE-ALL")
    result.add_argument("--profile-dir", type=Path, default=Path(".playwright-patreon-profile"), help="Persistent browser profile directory")
    result.add_argument("--log-dir", type=Path, help="Directory for per-run Playwright logs (default: ./logs)")
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


def start_run_log(log_dir: Path | None = None) -> tuple[logging.Logger, Path]:
    """Create a fresh local log for this updater run."""
    directory = log_dir or (Path.cwd() / "logs")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"playwright-update-{stamp}.log"
    logger = logging.getLogger(f"patreon_updater.playwright.{stamp}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("Updater run started. Sensitive post content and MEGA URLs are not logged.")
    return logger, path


def editor_control(page, role: str, control: str, args, logger: logging.Logger | None = None):
    override = getattr(args, control + "_name", None)
    language = getattr(args, "editor_language", "auto")
    languages = ["en", "zh"] if language == "auto" else [language]
    names = [override] if override else [name for lang in languages for name in EDITOR_LABELS[lang][control]]
    pattern = re.compile("^(?:" + "|".join(re.escape(name) for name in names) + ")$", re.IGNORECASE)
    locator = page.get_by_role(role, name=pattern)
    count = locator.count()
    if logger:
        logger.info("Control lookup: %s; role=%s; recognized labels=%s; matches=%s", control, role, names, count)
    # Patreon can expose both a text-labeled "insert link" action and an
    # icon-only rich-text toolbar button under the same accessible name. For
    # editing an existing selected hyperlink, use the explicitly labeled
    # toolbar control (aria-label/title) to avoid a page-wide strict-mode
    # ambiguity or clicking the composer-level insert action.
    if control == "link_button" and count != 1:
        for attribute in ("aria-label", "title"):
            for name in names:
                # Keep non-ASCII labels literal in CSS strings; JSON's default
                # \uXXXX escaping is not valid CSS string escaping.
                css_value = json.dumps(name, ensure_ascii=False)
                labeled = page.locator(f"[{attribute}={css_value}]")
                role_match = page.get_by_role("button", name=name, exact=True)
                specific = role_match.and_(labeled)
                specific_count = specific.count()
                if logger:
                    logger.info(
                        "Link button disambiguation: attribute=%s; label=%r; role_matches=%s; attribute_matches=%s; combined_matches=%s",
                        attribute, name, role_match.count(), labeled.count(), specific_count,
                    )
                if specific_count == 1:
                    if logger:
                        logger.info("Resolved ambiguous link control using accessible button %s=%r", attribute, name)
                    locator = specific
                    count = 1
                    break
            if count == 1:
                break
        if count != 1 and logger:
            logger.error("Link control remains ambiguous after aria-label/title disambiguation; matches=%s", count)
    # Playwright strict matching rejects ambiguous controls rather than picking one.
    try:
        if count != 1:
            raise RuntimeError(f"Expected one {control}, found {count}")
        locator.wait_for(state="visible", timeout=10000)
    except Exception as error:
        if logger:
            try:
                buttons = page.get_by_role("button").evaluate_all(
                    "elements => elements.slice(0, 40).map(e => ({text: (e.innerText || '').trim().slice(0, 80), aria: e.getAttribute('aria-label'), title: e.getAttribute('title')}))"
                )
            except Exception:
                buttons = "Could not inspect visible buttons"
            logger.error("Control lookup failed: %s; button diagnostics=%r; exception=%s", control, buttons, type(error).__name__)
        raise RuntimeError(
            f"Could not uniquely identify the {control.replace('_', ' ')} (matching controls: {count}). "
            f"Check the Playwright log for button details. Supported labels: {', '.join(names)}"
        ) from error
    return locator


def apply_replacement(page, item: Replacement, args: argparse.Namespace, logger: logging.Logger | None = None) -> None:
    """Use the recorded editor interaction and require confirmation before submit."""
    if logger:
        logger.info("Post %s link %s: navigating to edit page", item.post_id, item.link_number)
    page.goto(item.edit_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1_000)
    # These labels come from the user's Playwright codegen recording. They are
    # command-line options because Patreon localizes its editor UI.
    # Prefer the reviewed old URL itself over its visible text. Patreon may
    # render the same hyperlink with a localized or creator-chosen label.
    old_url_link = page.locator(f'a[href="{item.old_url}"]')
    target_count = old_url_link.count()
    if logger:
        logger.info("Post %s link %s: exact old-link anchors found=%s", item.post_id, item.link_number, target_count)
    if target_count > 0:
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
    if logger:
        logger.info("Post %s link %s: clicked target anchor; looking for link toolbar control", item.post_id, item.link_number)
    editor_control(page, "button", "link_button", args, logger).click()
    if logger:
        logger.info("Post %s link %s: link toolbar opened; locating URL field", item.post_id, item.link_number)
    url_field = editor_control(page, "textbox", "url_field", args, logger)
    url_field.wait_for(state="visible")
    actual_old_url = url_field.input_value()
    if actual_old_url != item.old_url:
        if logger:
            logger.error("Post %s link %s: URL field did not match expected old link (values intentionally omitted)", item.post_id, item.link_number)
        raise RuntimeError(
            f"Post {item.post_id}: editor URL differs from report; expected {item.old_url!r}, got {actual_old_url!r}. No change saved."
        )
    url_field.fill(item.new_url)
    if logger:
        logger.info("Post %s link %s: entered reviewed replacement; locating dialog save control", item.post_id, item.link_number)
    editor_control(page, "button", "save_button", args, logger).click()
    if not args.auto_confirm:
        confirmation = input(
            f"Replacement is prepared for post {item.post_id}. Review the visible browser, then type UPDATE to press Patreon's Update button (anything else cancels): "
        )
        if confirmation != "UPDATE":
            raise RuntimeError(f"Post {item.post_id}: update cancelled before submission.")
    if logger:
        logger.info("Post %s link %s: submitting Patreon post update", item.post_id, item.link_number)
    editor_control(page, "button", "update_button", args, logger).click()
    # Do not close the browser immediately after clicking Update: Patreon is a
    # single-page app and an in-flight save can otherwise be interrupted.
    page.wait_for_timeout(args.save_wait_seconds * 1_000)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1_500)
    saved_link = page.locator(f'a[href="{item.new_url}"]')
    if saved_link.count() == 0:
        if logger:
            logger.error("Post %s link %s: new link was not found after reload", item.post_id, item.link_number)
        raise RuntimeError(
            f"Post {item.post_id}: Patreon did not show the new URL after reloading. "
            "The browser remains open so you can inspect the editor; do not assume the update succeeded."
        )
    if logger:
        logger.info("Post %s link %s: replacement verified after reload", item.post_id, item.link_number)


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
    if args.link_number is not None and args.link_number < 1:
        parser().error("--link-number must be at least 1")
    if not args.report.is_file():
        parser().error(f"Report does not exist: {args.report}")
    candidates = load_replacements(args.report)
    if args.post_id:
        candidates = [item for item in candidates if item.post_id == args.post_id]
        if args.link_number is not None:
            candidates = [item for item in candidates if item.link_number == args.link_number]
    elif args.link_number is not None:
        parser().error("--link-number requires --post-id")
    elif not args.all:
        # Defaulting to a dry-run list prevents accidental write operations.
        args.apply = False
    if args.all and args.apply and args.confirm != "REPLACE-ALL":
        parser().error("Batch edits require --confirm REPLACE-ALL")
    if args.post_id and not candidates:
        suffix = f" and link {args.link_number}" if args.link_number is not None else ""
        parser().error(f"No replacement candidate found for post ID {args.post_id}{suffix}")
    if not candidates:
        print("No replacement candidates found.")
        return 0
    for item in candidates:
        print(f"{item.post_id} | {item.title} | Link {item.link_number} | {item.folder_name}\n  OLD {item.old_url}\n  NEW {item.new_url}\n  EDIT {item.edit_url}")
    if not args.apply:
        print("\nDry run only. Nothing was changed. Use --post-id ID --apply after reviewing one mapping.")
        return 0
    try:
        logger, log_path = start_run_log(args.log_dir)
    except OSError as error:
        print(f"Could not create the Playwright log: {error}")
        return 2
    print(f"Playwright log: {log_path}")
    try:
        if getattr(sys, "frozen", False):
            # Matches the browser location used by the PyInstaller build script.
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright import failed")
        logger.info("Updater run ended before browser startup")
        for handler in logger.handlers:
            handler.close()
            logger.removeHandler(handler)
        print("Playwright is not installed. Run: python -m pip install -e .[browser] && python -m playwright install chromium")
        return 2
    try:
        args.profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch_persistent_context(str(args.profile_dir), headless=False)
            page = browser.pages[0] if browser.pages else browser.new_page()
            try:
                logger.info("Visible Chromium browser started")
                page.goto("https://www.patreon.com/login", wait_until="domcontentloaded")
                if args.auto_confirm:
                    logger.info("Waiting for Patreon login session")
                    wait_for_login(page)
                else:
                    logger.info("Waiting for user to complete Patreon login")
                    input("Log in to Patreon in the opened browser, then press Enter here to begin the reviewed update(s)... ")
                for item in candidates:
                    try:
                        apply_replacement(page, item, args, logger)
                    except Exception as error:
                        logger.error("Post %s link %s failed during update; exception=%s", item.post_id, item.link_number, type(error).__name__)
                        raise
                    print(f"Verified updated post {item.post_id}: {item.old_url} -> {item.new_url}")
            except Exception as error:
                logger.error("Updater stopped; exception=%s", type(error).__name__)
                hold_error_open(error)
                return 1
            finally:
                logger.info("Closing browser context")
                browser.close()
    except Exception as error:
        logger.error("Browser startup/runtime failure; exception=%s", type(error).__name__)
        hold_error_open(error)
        return 1
    finally:
        logger.info("Updater run finished")
        for handler in logger.handlers:
            handler.flush()
            handler.close()
            logger.removeHandler(handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

