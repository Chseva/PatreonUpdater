# Patreon Updater

Version: **v1.0.1**

Patreon Updater finds outdated MEGA folder links in published Patreon posts and, after review, replaces them with the current links from your local MEGA listing.

It uses the Patreon API to create the report. Playwright is used only when you choose to update a Patreon post; it opens the post's direct `/edit` page in a visible browser.

## What it does

1. Reads your local MEGA folder listing, where each folder name has its current link.
2. Retrieves every published post in a Patreon campaign through Patreon API v2, following pagination automatically.
3. Extracts MEGA folder links from each post's content.
4. Compares post links with the local listing.
5. Writes a Markdown report and a JSON report.
6. Identifies replacement candidates using a saved manual mapping or a matching post title when the post's MEGA URL differs from the listed folder's current URL.
7. Lets you review and update one post or all reviewed candidates with the desktop app.

Enter your creator API token and the app automatically discovers your Patreon campaign before retrieving its posts. If multiple campaigns are returned, the desktop app asks you to choose one. There is no built-in campaign ID.

The token needs `campaigns` permission for discovery and `campaigns.posts` permission for reading posts. See the [Patreon API documentation](https://docs.patreon.com/). A missing campaign, rejected token, or denied discovery request produces an error message.

## Recommended: Windows desktop app

Run from source after installation:

```powershell
python -m patreon_mega_audit.gui
```

In the app:

1. Choose your MEGA listing text file. The field is blank by default, so it works with any location or filename.
2. Select **Generate report** and enter your Patreon API token.
3. Review the replacement candidates table. Each row shows the Patreon post ID, title, old post link, current local link, and direct edit URL.
4. If a post needs help matching its folder, open **Manage mappings** and follow the instructions below.
5. Select a row and choose **Update selected post**, or choose **Update all posts** after reviewing every listed change.

The first update opens a visible Chromium browser. Sign in to Patreon there if needed. The app reuses that local browser profile on later runs. The app confirmation is the approval to submit the update; it does not require terminal input or typing `UPDATE`.

Use **Settings** to change the post-save verification wait or choose **Forget saved token**. The wait must be at least one second.

Reports, the verification-wait setting, and the Playwright login profile are stored beside the source app when running from source. In the packaged EXE, they are stored under `%LOCALAPPDATA%\Patreon Updater\`.

## Understanding the report

Folder listings may contain simple names (`Alina`) or paths (`2025/Alina`). Automatic title matching uses the final folder name, so both match a post titled `【Look】 Alina`. Reports and the mapping dropdown retain the full path. If different paths have the same final name, choose the correct path in **Manage mappings**. Individual MEGA file links in recursive listings are ignored; this app matches folder links.

Saved manual mappings use the listing's exact label. When switching from a short listing to a recursive listing, an existing mapping to `Alina` may need to be changed to `2025/Alina`.

### Manual post-to-folder mappings

Use **Manage mappings** when a Patreon post's title does not match its MEGA folder name, or when you want to override an automatic match. Posts already matched correctly do not need a manual mapping.

Generate a report during the current app session first. The mapping window lists posts containing detected MEGA links, including posts that have no replacement candidate yet.

| Column | Meaning |
| --- | --- |
| Patreon post | The post title and its ID. Click a row to select the post you want to connect. |
| Saved folder | The folder you manually assigned. A blank cell means no manual mapping has been saved; automatic title matching may still apply. |
| Status | How the post was matched, or why it cannot be updated automatically. |

**The dropdown below the table lists folder names from your selected local MEGA listing.** Choose the folder that belongs to the selected Patreon post. Selecting a dropdown item alone does not save the connection.

For example, suppose a post is called **Summer release**, but its MEGA folder is called **Alina**:

1. Click **Summer release** in the post table.
2. Choose **Alina** from the dropdown below the table.
3. Click **Save mapping**. Alina appears in the **Saved folder** column.
4. Close the mapping window and review the refreshed replacement candidates in the main window.

Saving a mapping refreshes both reports immediately using the posts and listing loaded when you generated the report. It does not edit the Patreon post. A replacement candidate appears only if the supported single link in the post differs from the chosen folder's current link. Generate a fresh report if the Patreon content or local listing has changed.

Select a post and click **Remove mapping** to restore automatic title matching.

| Status | Meaning / next step |
| --- | --- |
| Title match | One folder matched the post title automatically. Check that it is the intended folder. |
| No folder match | No folder name matched the title. Select the correct folder and save a mapping. |
| Manual mapping | A saved post-to-folder connection is being used. This does not necessarily mean the link needs replacing. |
| Mapped folder missing from listing | The saved folder name is absent from the current listing. Check the listing or change the mapping. |
| Ambiguous folder name — choose a unique folder | More than one folder matched. Choose a uniquely named folder; duplicate names with different URLs must be clarified in the listing. |
| Multiple links — manual editing required | The post contains multiple distinct MEGA links and is excluded from automatic updates. |
| Invalid link — manual editing required | The detected MEGA URL is not a supported folder link and is excluded from automatic updates. |

Mappings are saved in `manual_mappings.json` in the app's data directory and reused for future reports, including command-line reports. They use the post ID and exact folder name, so post title changes and renewed folder URLs are supported. If you rename a folder, update its mapping. Missing or ambiguous folder names do not generate replacements.

Posts with multiple distinct MEGA links are marked **Multiple links — manual editing required** and excluded from automatic updates. Repeated occurrences of the same URL count as one distinct link. Invalid MEGA links are also excluded from updates. Manual mappings override title matching for supported single-link posts.

The mapping file contains post IDs and folder names and is excluded from Git by default. Keep it private alongside your reports.

### Report fields

Each applicable post includes its ID-derived URLs:

- Post: `https://www.patreon.com/posts/<post-id>`
- Edit page: `https://www.patreon.com/posts/<post-id>/edit`

Report terms:

- **Referenced folders** — a MEGA URL in the post exactly matches the current local listing.
- **Missing or stale candidates** — a valid MEGA folder link appears in the post but is not an exact URL match in the listing.
- **Replacement candidates** — a manual mapping or the post title identifies one folder in the listing, and the post's single supported MEGA link differs from that folder's current link. The JSON records both `old_post_url` and `new_listing_url`; these are the precise values used during an update.
- **Structurally invalid links** — MEGA URLs that do not use the expected `/folder/<id>#<key>` format.
- **Unreferenced local folders** — folders in the listing that are not found in a published post.

For safety, the updater locates the hyperlink by the exact old URL, checks it before editing, saves the new URL, reloads the edit page, and verifies that the new URL is present. It does not choose a link merely because its visible label says “Mega”.

## Install from source

Requires Windows and Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[browser,dev]"
python -m playwright install chromium
```

`.[browser,dev]` installs Playwright and the test tools. For reports only, `python -m pip install -e .` is enough.

## Command line

Generate both reports:

```powershell
python -m patreon_mega_audit `
  --mega-listing "C:\path\to\MEGA folder links.txt" `
  --output outputs\patreon_mega_report.md `
  --json-output outputs\patreon_mega_report.json
```

The token is requested with hidden input and the campaign is discovered automatically. Advanced users can pass `--campaign-id` to override discovery; this is required when the command line discovers multiple campaigns. This command does not open a browser or change any Patreon post.

Preview candidates without editing:

```powershell
python -m patreon_mega_audit.update_posts --report outputs\patreon_mega_report.json
```

Apply one reviewed candidate:

```powershell
python -m patreon_mega_audit.update_posts `
  --report outputs\patreon_mega_report.json `
  --post-id YOUR_POST_ID `
  --apply
```

Replace `YOUR_POST_ID` with the post ID from your reviewed report.

Applying every candidate requires the deliberate batch confirmation:

```powershell
python -m patreon_mega_audit.update_posts `
  --report outputs\patreon_mega_report.json `
  --all --apply --confirm REPLACE-ALL
```

The command-line updater uses a persistent browser profile at `.playwright-patreon-profile` by default. Editor controls default to automatic English/Chinese label detection. In the desktop app, **Settings → Patreon editor language** offers Automatic, English, and Chinese. The command-line equivalent is `--editor-language auto`, `en`, or `zh`. Exact-label command-line overrides remain available for other labels. Unrecognized or ambiguous controls stop the update; the old URL is still checked before replacement. English and Chinese label variants need verification against your live Patreon editor.

The build scripts use `Patreon Updater.spec`, which excludes Playwright's `.local-browsers/.links/` installation metadata while keeping the bundled browser files.

## Token and privacy

The desktop app can remember a Patreon API token only if you select that option. It stores the token in Windows Credential Manager for the current Windows user, never in a report or plain-text settings file. **Settings → Forget saved token** removes it.

Do not share your API token, MEGA listing, generated reports, `%LOCALAPPDATA%\Patreon Updater\`, or `.playwright-patreon-profile`. The browser profile may contain your Patreon sign-in session.

## Build a shareable Windows app

From the project folder, run:

```powershell
.\scripts\build_windows.cmd
```

This creates `dist\Patreon Updater\`. Zip and share the entire folder, including both `Patreon Updater.exe` and `_internal`. Recipients do not need to install Python, Playwright, or Chromium separately. They do need their own Patreon API token and must sign in to Patreon in the browser opened by the app.

## Test

```powershell
python -m pytest
```
