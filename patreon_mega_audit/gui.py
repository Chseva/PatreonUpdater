"""Tkinter desktop UI for the Patreon MEGA audit and update workflow."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .app_paths import data_root, is_frozen, runtime_root
from . import __version__
from .credential_store import delete_token, load_token, save_token
from .mega import read_listing
from .mappings import load_mappings, save_mappings
from .patreon import PatreonApiError, PatreonClient
from .report import build_report, render_markdown
from .update_posts import Replacement, load_replacements

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = data_root()
DEFAULT_REPORT = DATA_ROOT / "outputs" / "patreon_mega_report.json"
DEFAULT_MARKDOWN = DATA_ROOT / "outputs" / "patreon_mega_report.md"
SETTINGS_FILE = DATA_ROOT / "patreon_updater_settings.json"
MAPPINGS_FILE = DATA_ROOT / "manual_mappings.json"


class TokenDialog(simpledialog.Dialog):
    """Secure token entry with explicit Windows Credential Manager opt-in."""

    def body(self, master: tk.Misc):
        ttk.Label(master, text="Patreon API token:").grid(row=0, column=0, sticky="w")
        self.token = ttk.Entry(master, show="*", width=54)
        self.token.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.remember = tk.BooleanVar(value=True)
        ttk.Checkbutton(master, text="Remember securely in Windows Credential Manager", variable=self.remember).grid(row=2, column=0, sticky="w")
        ttk.Label(master, text="The token is never saved in the report or a plain-text file.", foreground="#555555").grid(row=3, column=0, sticky="w", pady=(4, 0))
        return self.token

    def apply(self) -> None:
        self.result = (self.token.get().strip(), self.remember.get())


class SettingsDialog(simpledialog.Dialog):
    """Non-sensitive application settings."""

    def __init__(self, parent: tk.Misc, wait_seconds: int, forget_callback, language="auto") -> None:
        self.language = language
        self.wait_seconds = wait_seconds
        self.forget_callback = forget_callback
        super().__init__(parent, title="Patreon Updater settings")

    def body(self, master: tk.Misc):
        ttk.Label(master, text="Seconds to wait after Patreon Update before verifying:").grid(row=0, column=0, sticky="w")
        self.wait_var = tk.StringVar(value=str(self.wait_seconds))
        ttk.Spinbox(master, from_=1, to=60, textvariable=self.wait_var, width=7).grid(row=0, column=1, padx=(10, 0), sticky="w")
        ttk.Label(master, text="This does not store your API token.", foreground="#555555").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 12))
        ttk.Button(master, text="Forget saved token", command=self.forget_callback).grid(row=2, column=0, sticky="w")
        ttk.Label(master, text="Patreon editor language:").grid(row=3, column=0, sticky="w", pady=10)
        labels = {"auto": "Automatic", "en": "English", "zh": "Chinese"}
        self.language_var = tk.StringVar(value=labels[self.language])
        ttk.Combobox(master, state="readonly", values=list(labels.values()), textvariable=self.language_var, width=12).grid(row=3, column=1)
        return None

    def validate(self) -> bool:
        try:
            value = int(self.wait_var.get())
        except ValueError:
            value = 0
        if value < 1:
            messagebox.showerror("Patreon Updater", "The wait must be at least 1 second.", parent=self)
            return False
        self.wait_seconds = value
        return True

    def apply(self) -> None:
        self.result = (self.wait_seconds, {"Automatic": "auto", "English": "en", "Chinese": "zh"}[self.language_var.get()])


class PatreonUpdaterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Patreon Updater v{__version__}")
        self.minsize(1060, 620)
        self.listing_path = tk.StringVar(value="")
        self.status = tk.StringVar(value="Generate a report to review replacement candidates.")
        self.save_wait_seconds = self._load_settings()
        self.candidates: list[Replacement] = []
        self.audit_posts = None
        self.audit_folders = None
        self._set_icon()
        self._build()
        if DEFAULT_REPORT.is_file():
            self.load_report()

    def _set_icon(self) -> None:
        icon = runtime_root() / "assets" / "PU.ico"
        if icon.is_file():
            self.iconbitmap(default=str(icon))

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text="MEGA listing:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(outer, textvariable=self.listing_path).grid(row=0, column=1, sticky="ew")
        ttk.Button(outer, text="Browse…", command=self.choose_listing).grid(row=0, column=2, padx=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 10))
        ttk.Button(actions, text="Generate report", command=self.generate_report).pack(side="left")
        ttk.Button(actions, text="Update selected post", command=self.update_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Update all posts", command=self.update_all).pack(side="left")
        ttk.Button(actions, text="Manage mappings", command=self.manage_mappings).pack(side="left", padx=8)
        ttk.Button(actions, text="Settings…", command=self.open_settings).pack(side="left", padx=8)
        ttk.Button(actions, text="Open report folder", command=self.open_report_folder).pack(side="right")

        columns = ("post_id", "title", "folder", "old_url", "new_url", "edit_url")
        self.table = ttk.Treeview(outer, columns=columns, show="headings", selectmode="browse")
        headings = {
            "post_id": ("Post ID", 105), "title": ("Post title", 220), "folder": ("Folder", 100),
            "old_url": ("Old post link", 270), "new_url": ("New listing link", 270), "edit_url": ("Direct edit URL", 260),
        }
        for column, (text, width) in headings.items():
            self.table.heading(column, text=text)
            self.table.column(column, width=width, minwidth=80, stretch=True)
        self.table.grid(row=2, column=0, columnspan=3, sticky="nsew")
        scroll_x = ttk.Scrollbar(outer, orient="horizontal", command=self.table.xview)
        scroll_x.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.table.configure(xscrollcommand=scroll_x.set)
        ttk.Label(outer, textvariable=self.status, anchor="w").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(outer, text="ⓘ", width=3, command=self.show_about).grid(row=4, column=2, sticky="e", pady=(10, 0))

    def choose_listing(self) -> None:
        selected = filedialog.askopenfilename(title="Select MEGA folder listing", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if selected:
            self.listing_path.set(selected)

    def _load_settings(self) -> int:
        self.editor_language = "auto"
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            language = settings.get("editor_language", "auto")
            self.editor_language = language if language in ("auto", "en", "zh") else "auto"
            value = int(settings.get("save_wait_seconds", 5))
            return max(1, value)
        except (OSError, ValueError, json.JSONDecodeError):
            return 5

    def _save_settings(self) -> None:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps({"save_wait_seconds": self.save_wait_seconds, "editor_language": self.editor_language}, indent=2), encoding="utf-8")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.save_wait_seconds, self.forget_token, self.editor_language)
        if dialog.result is not None:
            self.save_wait_seconds, self.editor_language = dialog.result
            self._save_settings()
            self.status.set(f"Settings saved. Post-save verification wait: {self.save_wait_seconds} second(s).")

    def generate_report(self) -> None:
        listing = Path(self.listing_path.get())
        if not listing.is_file():
            messagebox.showerror("Patreon Updater", "Choose an existing MEGA folder listing first.")
            return
        token = self.get_token()
        if not token:
            return
        self.status.set("Finding your Patreon campaign…")
        self._set_buttons_state("disabled")
        threading.Thread(target=self._discover_worker, args=(listing, token), daemon=True).start()

    def get_token(self) -> str | None:
        try:
            saved_token = load_token()
        except OSError as error:
            messagebox.showerror("Patreon Updater", f"Could not access Windows Credential Manager: {error}")
            return None
        if saved_token and messagebox.askyesno("Use saved token?", "Use the API token stored in Windows Credential Manager?"):
            return saved_token
        dialog = TokenDialog(self, title="Patreon Updater — API token")
        if not dialog.result:
            return None
        token, remember = dialog.result
        if not token:
            return None
        if remember:
            try:
                save_token(token)
            except Exception as error:
                messagebox.showerror("Patreon Updater", f"Could not save the token in Windows Credential Manager: {error}")
                return None
        return token

    def forget_token(self) -> None:
        if not messagebox.askyesno("Forget saved token?", "Remove the Patreon API token from Windows Credential Manager?"):
            return
        try:
            deleted = delete_token()
        except Exception as error:
            messagebox.showerror("Patreon Updater", f"Could not remove the saved token: {error}")
        else:
            messagebox.showinfo("Patreon Updater", "Saved token removed." if deleted else "No saved token was found.")

    def _discover_worker(self, listing: Path, token: str) -> None:
        try:
            campaigns = PatreonClient(token).discover_campaigns()
            self.after(0, self._campaigns_found, listing, token, campaigns)
        except PatreonApiError as error:
            self.after(0, self._report_failed, str(error))

    def _campaigns_found(self, listing: Path, token: str, campaigns: list[str]) -> None:
        campaign_id = campaigns[0]
        if len(campaigns) > 1:
            choice = simpledialog.askinteger(
                "Choose Patreon campaign",
                "Multiple campaigns were found. Enter the number of the campaign to audit:\n\n"
                + "\n".join(f"{index}. Campaign {value}" for index, value in enumerate(campaigns, 1)),
                parent=self, minvalue=1, maxvalue=len(campaigns),
            )
            if choice is None:
                self._set_buttons_state("normal")
                self.status.set("Report generation cancelled.")
                return
            campaign_id = campaigns[choice - 1]
        self.status.set(f"Retrieving published posts for campaign {campaign_id}…")
        threading.Thread(target=self._generate_worker, args=(listing, token, campaign_id), daemon=True).start()

    def _generate_worker(self, listing: Path, token: str, campaign_id: str) -> None:
        try:
            local_folders = read_listing(listing)
            posts = [post for post in PatreonClient(token).iter_campaign_posts(campaign_id) if post.published_at]
            report = build_report(posts, local_folders, load_mappings(MAPPINGS_FILE))
            DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_REPORT.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
            DEFAULT_MARKDOWN.write_text(render_markdown(report), encoding="utf-8")
            self.after(0, self._report_finished, posts, local_folders)
        except (OSError, PatreonApiError, ValueError) as error:
            self.after(0, self._report_failed, str(error))

    def _report_finished(self, posts, folders) -> None:
        self.audit_posts = posts
        self.audit_folders = folders
        self._set_buttons_state("normal")
        self.load_report()
        self.status.set(f"Fetched {len(posts)} published posts. Reports saved in outputs.")

    def manage_mappings(self) -> None:
        if self.audit_posts is None:
            messagebox.showinfo("Manage mappings", "Generate a report first to load your posts and folders.")
            return
        try:
            mappings = load_mappings(MAPPINGS_FILE)
        except (OSError, ValueError) as error:
            messagebox.showerror("Manage mappings", str(error))
            return
        dialog = tk.Toplevel(self)
        dialog.title("Manage mappings")
        dialog.geometry("850x480")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Select a post and its MEGA folder. Saved mappings override title matching.").pack(anchor="w")
        tree = ttk.Treeview(frame, columns=("title", "folder", "status"), show="headings", selectmode="browse")
        for column, label in (("title", "Patreon post"), ("folder", "Saved folder"), ("status", "Status")):
            tree.heading(column, text=label)
        tree.pack(fill="both", expand=True, pady=10)
        folder_names = sorted({folder.name for folder in self.audit_folders})
        picker = ttk.Combobox(frame, values=folder_names, state="readonly", width=65)
        picker.pack(fill="x", pady=5)

        def refresh():
            selected = tree.selection()
            tree.delete(*tree.get_children())
            report = build_report(self.audit_posts, self.audit_folders, mappings)
            for post in report.posts_with_mega_links:
                tree.insert("", "end", iid=post.post_id, values=(f"{post.title} ({post.post_id})", mappings.get(post.post_id, ""), post.update_status))
            if selected and tree.exists(selected[0]):
                tree.selection_set(selected[0])

        def choose(event=None):
            selected = tree.selection()
            if selected:
                picker.set(mappings.get(selected[0], ""))

        def change(remove=False):
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Manage mappings", "Select a post first.", parent=dialog)
                return
            post_id = selected[0]
            updated = dict(mappings)
            if remove:
                updated.pop(post_id, None)
            else:
                name = picker.get()
                matches = {folder.url for folder in self.audit_folders if folder.name == name}
                if len(matches) != 1:
                    messagebox.showerror("Manage mappings", "Choose a folder with a unique name in your listing.", parent=dialog)
                    return
                status = tree.item(post_id, "values")[2]
                if "manual editing required" in status:
                    messagebox.showinfo("Manage mappings", status, parent=dialog)
                    return
                updated[post_id] = name
            try:
                save_mappings(MAPPINGS_FILE, updated)
                report = build_report(self.audit_posts, self.audit_folders, updated)
                DEFAULT_REPORT.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
                DEFAULT_MARKDOWN.write_text(render_markdown(report), encoding="utf-8")
            except (OSError, ValueError) as error:
                messagebox.showerror("Manage mappings", str(error), parent=dialog)
                return
            mappings.clear()
            mappings.update(updated)
            refresh()
            self.load_report()

        tree.bind("<<TreeviewSelect>>", choose)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Save mapping", command=change).pack(side="left")
        ttk.Button(buttons, text="Remove mapping", command=lambda: change(True)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")
        refresh()

    def _report_failed(self, error: str) -> None:
        self._set_buttons_state("normal")
        self.status.set("Report generation failed.")
        messagebox.showerror("Patreon Updater", error)

    def _set_buttons_state(self, state: str) -> None:
        # The UI has only a few buttons and child traversal is sufficient here.
        for child in self.winfo_children():
            self._set_child_state(child, state)

    def _set_child_state(self, widget: tk.Misc, state: str) -> None:
        if isinstance(widget, ttk.Button):
            widget.configure(state=state)
        for child in widget.winfo_children():
            self._set_child_state(child, state)

    def load_report(self) -> None:
        if not DEFAULT_REPORT.is_file():
            messagebox.showinfo("Patreon Updater", "No report exists yet. Generate one first.")
            return
        try:
            self.candidates = load_replacements(DEFAULT_REPORT)
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror("Patreon Updater", f"Could not load report: {error}")
            return
        self.table.delete(*self.table.get_children())
        for index, item in enumerate(self.candidates):
            self.table.insert("", "end", iid=str(index), values=(item.post_id, item.title, item.folder_name, item.old_url, item.new_url, item.edit_url))
        self.status.set(f"Loaded {len(self.candidates)} reviewed replacement candidate(s).")

    def update_selected(self) -> None:
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Patreon Updater", "Select one replacement candidate first.")
            return
        item = self.candidates[int(selection[0])]
        same_post = [candidate for candidate in self.candidates if candidate.post_id == item.post_id]
        details = "\n".join(f"OLD: {candidate.old_url}\nNEW: {candidate.new_url}" for candidate in same_post)
        approved = messagebox.askyesno(
            "Launch reviewed update?",
            f"A visible Playwright browser will open for post {item.post_id}: {item.title}.\n\n{details}\n\n"
            "This will submit the reviewed replacement automatically using the saved Playwright login session. "
            "If Patreon requires login, it will stop without changing the post. Continue?",
        )
        if not approved:
            return
        command = [
            *self._updater_command(), "--report", str(DEFAULT_REPORT),
            "--post-id", item.post_id, "--apply", "--auto-confirm", "--save-wait-seconds", str(self.save_wait_seconds),
            "--profile-dir", str(DATA_ROOT / ".playwright-patreon-profile"),
        ]
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(command, cwd=DATA_ROOT, creationflags=creation_flags)
        self.status.set(f"Opened guarded updater for post {item.post_id}.")

    def update_all(self) -> None:
        if not self.candidates:
            messagebox.showinfo("Patreon Updater", "There are no replacement candidates to update.")
            return
        details = "\n".join(f"{item.post_id} — {item.title}: {item.old_url} → {item.new_url}" for item in self.candidates)
        approved = messagebox.askyesno(
            "Update all posts?",
            f"This will open the guarded Playwright updater for all {len(self.candidates)} replacement candidate(s):\n\n{details}\n\n"
            "This will submit the reviewed replacements automatically using the saved Playwright login session. "
            "If Patreon requires login, it will stop without changing any posts. Continue?",
        )
        if not approved:
            return
        command = [
            *self._updater_command(), "--report", str(DEFAULT_REPORT),
            "--all", "--apply", "--confirm", "REPLACE-ALL", "--auto-confirm", "--save-wait-seconds", str(self.save_wait_seconds),
            "--profile-dir", str(DATA_ROOT / ".playwright-patreon-profile"),
        ]
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(command, cwd=DATA_ROOT, creationflags=creation_flags)
        self.status.set(f"Opened guarded batch updater for {len(self.candidates)} candidate(s).")

    def show_about(self) -> None:
        about = tk.Toplevel(self)
        about.title(f"About Patreon Updater v{__version__}")
        about.resizable(False, False)
        about.transient(self)
        about.grab_set()
        frame = ttk.Frame(about, padding=(48, 28, 48, 24))
        frame.grid(sticky="nsew")
        ttk.Label(frame, text=f"Patreon Updater v{__version__}", font=("Courier New", 14, "bold")).grid(row=0, column=0, pady=(0, 16))
        ttk.Label(frame, text="Created by").grid(row=1, column=0)
        ttk.Label(frame, text="J. D.").grid(row=2, column=0, pady=(6, 18))
        ttk.Label(frame, text="Patreon").grid(row=3, column=0)
        link = tk.Label(frame, text="patreon.com/chseva", fg="#1f4f8a", cursor="hand2", font=("TkDefaultFont", 8, "underline"))
        link.grid(row=4, column=0, pady=(5, 20))
        link.bind("<Button-1>", lambda _event: webbrowser.open("https://www.patreon.com/chseva"))
        ttk.Button(frame, text="OK", command=about.destroy, width=11).grid(row=5, column=0)

    def _updater_command(self) -> list[str]:
        if is_frozen():
            return [sys.executable, "--run-updater", "--editor-language", self.editor_language]
        return [sys.executable, "-m", "patreon_mega_audit.update_posts", "--editor-language", self.editor_language]

    def open_report_folder(self) -> None:
        DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(DEFAULT_REPORT.parent)])


def main() -> int:
    app = PatreonUpdaterApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
