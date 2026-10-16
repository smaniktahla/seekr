# Working on Seekr

## Change workflow

- After the initial repository bootstrap, every change must use a pull request. Do not commit or push directly to `main`.
- Create a focused `codex/<topic>` branch (and an isolated worktree when sharing a checkout with another session).
- Run relevant tests and compile the Windows client when it changes. Explain behavior changes, validation, and material limits in the PR.
- Do not merge or deploy unless the user's current request authorizes it. A merged PR does not automatically deploy.
- Keep changes to the Windows client, NAS service, and external assistant integrations distinct and identify which components need updating.

## Private configuration and artifacts

- This repository is public. Never commit access tokens, DPAPI credentials, `.env`, local client configuration, database/index files, extracted document text, source-document names, inventory reports, personal filesystem paths, logs, or production screenshots.
- Use example configuration with placeholders. Keep host addresses and dataset paths in private runtime configuration.
- Do not read credential stores or print secrets. Use normal Git/CLI authentication or the user's configured connector.
- Do not add a license on the user's behalf; ask which license they want if licensing is requested.

## Deployment

- The user's Windows production installation is `C:\ArchiveSearch`. Build outputs in the checkout are not the production installation.
- Preserve the production credential and user preferences. Do not close an open app or overwrite an in-use binary; stage a new version and update the shortcut when deployment is authorized.
- Mount source shares read-only. Keep the index separately. Never delete or modify source documents as part of search maintenance.
- The NAS deployment uses Docker Compose with persistent `data/`. Preserve it during upgrades.
- Needle/Nina is maintained in a separate repository and must follow that repository's PR and deployment rules; do not edit an obsolete development tree or running release.

## Checks

```sh
python -m unittest discover -s . -p test_core.py -v
python -m compileall -q core.py extract.py indexer.py worker.py server.py start.py mcp_proxy.py
```

On Windows, run `./scripts/build-windows.ps1`. See README for dependencies and deployment details.
