# Seekr

Fast search for a personal archive on a NAS, with a native VB.NET Windows client, a browser interface, and MCP tools for AI assistants.

The server indexes filenames immediately, then extracts document text and media metadata in the background. Source shares are mounted read-only. Searches run against a persistent SQLite FTS5 index rather than scanning source documents on every query.

## Features

- Four configurable source shares: Documents, Pictures, Music, and Videos.
- Native Windows search, preview, file-type column, Open Original, Show in Explorer, Copy path, and right-click actions.
- Search as you type: literal filename/path substring matching after a 250ms pause and at least two characters. Stale requests are cancelled and their results discarded.
- Enter/Search runs full-text search. Optional local semantic/hybrid retrieval uses Ollama's `nomic-embed-text` model.
- Type/share filters, remembered preferences, and optional filter clearing after explicit searches. Live updates preserve filters; pagination preserves the original query.
- MCP tools: `archive_search`, `archive_read`, and `archive_status`, exposed through authenticated Streamable HTTP or a stdio bridge.
- Resumable extraction, six-hour incremental inventories, and separate indexing status for pending files, failures, OCR needs, and size limits.

## Run the server

Requirements: Docker with Compose, source datasets, and persistent space for the index. Ollama is optional; keyword and filename searches work independently.

1. Copy `.env.example` to `.env` and replace every placeholder. Use a long random `ARCHIVE_TOKEN`.
2. Set `ARCHIVE_DATA_ROOT` to the parent of your Documents, Pictures, Music and Videos datasets, or edit the read-only bind mounts in `compose.yaml`.
3. `ARCHIVE_BIND_IP` defaults to localhost. Set the NAS's private LAN address if other devices must connect. Do not expose this HTTP endpoint publicly without TLS and appropriate network controls.
4. Run:

```sh
docker compose up -d --build
```

The web interface is on port 8093. Basic-auth username: `archive`; password: the configured archive token. API/MCP clients use `Authorization: Bearer <token>`. `/health` is unauthenticated and returns no document information.

The container has a 1536MB memory ceiling and a 1.5 CPU ceiling. Serving and background ingestion share those limits. Its index is stored in `./data/`; preserve that directory during upgrades. The source mount paths inside the container are `/archive/<share>`.

## Build and configure Windows

Requirements: Windows with .NET Framework 4.x and its VB compiler.

```powershell
./scripts/build-windows.ps1
```

The build produces `build/windows/ArchiveSearch.exe` and its icon. Copy them to your chosen install directory. Copy `client.example.json` there as `client.json` and set the service URL. Alternatively, set the `ARCHIVE_SEARCH_URL` environment variable. The fallback endpoint is localhost:8093.

Provision a Windows-account-encrypted credential:

```powershell
./scripts/set-client-token.ps1 -InstallDirectory C:\ArchiveSearch
```

Enter the same token configured on the server. Keep `archive-token.dpapi` beside the executable. The credential is tied to the current Windows account; it is not portable between accounts. Preferences are stored under the current user's Local AppData directory.

Originals open using Windows file associations and the `\\truenas\<share>\...` path returned by the server. The current pilot assumes that SMB hostname; adjust `core.public()` if your share hostname differs. The Windows account needs ordinary SMB access. A browser can download a copy or show the SMB path, but cannot reliably launch the original in Office.

## MCP

HTTP endpoint: `http://your-nas:8093/mcp`, with Bearer authentication. The stdio bridge avoids credentials in command arguments:

```sh
python mcp_proxy.py --url http://your-nas:8093/mcp --token-file /private/path/token
```

Windows can instead use `--dpapi-file C:\ArchiveSearch\archive-token.dpapi`. Register the command using your AI application's MCP configuration. Keep tokens and actual client configurations outside the repository. Needle/Nina can route simple archive requests to this API; its maintained integration belongs in its own repository.

## Coverage and limits

- Document extraction: PDF; modern and legacy Word, Excel and PowerPoint; RTF; OpenDocument; plain text, Markdown, CSV, HTML and SQL.
- XLSX includes sheet names and cell coordinates; XLS includes sheet names and row/column numbers. Values are saved/cached values: formulas are not recalculated and macros are not run.
- Media extraction: EXIF and selected image tags, music tags, video format metadata.
- Pilot limits: 300,000 extracted characters, 500 PDF pages, 200MB document size, and 35 seconds per extraction worker. Truncation and special states are reported.
- Scanned PDFs may be marked `needs_ocr`; OCR is not implemented. Image understanding, audio/video transcription, archive expansion and Access database content extraction are not implemented.
- One semantic vector represents each document's filename/path/metadata and its opening 6,000 characters. Semantic search does not cover every passage. Inspect status for current vector coverage.
- Filename mode ANDs literal, space-separated path fragments. Wildcard syntax is not implemented; `%` and `_` are literal characters. Keyword mode ANDs literal words.
- Backed-up source files can lag their originals. Indexing catches up after the next copy and inventory pass. Deletions are pruned only after an error-free traversal of the affected share.

## Tests and contributions

## Settings, configurable folders, exact duplicates, and DocMost

The Windows **Settings...** dialog edits the selected service's source folders, duplicate visibility and DocMost connection. Its connection section can switch between the NAS endpoint and a localhost service; a different token can be entered without writing it to plain-text configuration. Per-service tokens are encrypted with Windows DPAPI. No source paths or credentials belong in this public repository.

Each source has a stable ID, a **server folder** the indexing service can read, an **open path** used by Windows, and an enabled flag. Existing default IDs preserve the original index paths. Disabling a source hides its results without deleting originals. Removing a source or changing its root removes only its indexed records and queues a rescan. Saving requires authenticated service access. The live configuration is stored atomically in `data/settings.json` (or `ARCHIVE_SETTINGS`), not in the repository. `settings.example.json` documents the schema.

For Docker on a NAS, folders must already be mounted read-only inside `/archive`; the Settings dialog cannot create Docker mounts. `ARCHIVE_ALLOWED_ROOT=/archive` restricts configurable roots in the supplied Compose stack. Set the Windows open path to the corresponding SMB path. A NAS service cannot read a laptop `C:` folder.

For native Windows indexing, start a local service explicitly:

```powershell
./scripts/run-local.ps1 -Folders 'C:\YourDocuments','\\your-nas\Documents' -ClientInstallDirectory C:\ArchiveSearch
```

The launcher creates an isolated Python environment, installs requirements, creates a separate local index under Local AppData, and listens on loopback only. It reuses the current user's DPAPI-protected client token without putting it in process arguments. It runs in the foreground; Ctrl+C stops it. Existing local settings are preserved on subsequent launches; edit them from Settings. Choose **Use local** in Settings to connect. The local service may index both local and accessible SMB directories under the Windows user's permissions. This release switches between service indexes; it does not federate independent laptop and NAS indexes.

Modern Office, PDF, text, image and audio extraction have native Python paths. Legacy Word/PowerPoint and RTF need external `antiword`/`catppt`/`unrtf` utilities. Install `ffprobe` for video metadata and ExifTool for broader image formats; without optional helpers some formats remain filename/metadata-only or report an extraction failure. OCR and video transcription remain out of scope.

**Hide exact duplicate files** uses SHA-256 hashes computed in the background only for size-collision candidates. Same name/size alone never hides a result. Unhashed or changed files remain visible until verified. No originals are deleted. Turn the option off to show all copies. Hashing large duplicate candidates can require substantial disk reads. Deduplication chooses a representative from the current matching set, so a matching filename is not hidden just because a different copy has another name. The grouping happens within each service, not across independent local/NAS indexes.

The optional **DocMost** connector uses only MCP `search_notes` / `get_note`, plus the provided read-only semantic search API. It never writes notes, logs into DocMost, or accesses Postgres. Normal full-text searches interleave file and note results with stable pagination. Live typing searches file paths; selecting the DocMost source explicitly uses DocMost's word matching. Semantic DocMost results follow its own ingestion schedule. Results are capped at 20 notes per query and multiple matching chunks from one note are grouped. Connector outages leave file results available with a warning. DocMost endpoint URLs are private runtime settings; archive authentication is not forwarded to them.

Notes can be read in Seekr's preview. **Open** launches the configured DocMost app. For a direct page link, supply a verified HTTP(S) page URL template containing `{id}`; the connector does not invent a deep-link route from the note ID.

Upgrade both the NAS backend and Windows executable for these settings features. Database migration adds nullable hash fields without changing originals. Keep `data/` and the authentication token; rebuild the container from the updated source. No DocMost restart is needed. The previous clear-search button is included in this feature branch.

### Validation

Run all regressions, including the optional authenticated API tests when service dependencies are installed:

```sh
python -m unittest discover -s . -p 'test_*.py' -v
```

```sh
python -m unittest discover -s . -p test_core.py -v
```

CI runs backend regression tests and Windows compilation. Deployment smoke tests require a configured private service and credential; they are not run by public CI. `ArchiveSearch.exe --smoke-live` validates filename results and cancellation against a particular sample query, so adapt that private smoke scenario for your archive.

**All changes after the initial import go through pull requests.** Read [AGENTS.md](AGENTS.md) before making changes. No deployment is triggered automatically by CI.
