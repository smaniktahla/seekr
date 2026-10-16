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

```sh
python -m unittest discover -s . -p test_core.py -v
```

CI runs backend regression tests and Windows compilation. Deployment smoke tests require a configured private service and credential; they are not run by public CI. `ArchiveSearch.exe --smoke-live` validates filename results and cancellation against a particular sample query, so adapt that private smoke scenario for your archive.

**All changes after the initial import go through pull requests.** Read [AGENTS.md](AGENTS.md) before making changes. No deployment is triggered automatically by CI.
