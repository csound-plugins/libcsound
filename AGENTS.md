# Agent notes

## Releases are tag-driven (setuptools-scm)

The package version is derived from git tags at build time
(`dynamic = ["version"]` + `[tool.setuptools_scm]` in `pyproject.toml`).
Never edit a version string to cut a release; tag instead:

    git tag 0.17.8 && git push --tags

Consequences: CI checkouts must fetch tags (`fetch-depth: 0`), and building
from a tree without git metadata (e.g. a GitHub "Download ZIP" archive) falls
back to `fallback_version` (sdists embed the frozen version in `PKG-INFO` and
are unaffected).

## Bundled installers are mirrors, do not edit them here

`libcsound/data/getcsound.sh` and `libcsound/data/getcsound.ps1` are generated
mirrors. The source of truth is `~/dev/csound/installer/` (see its `AGENTS.md`).

Never edit the files in `libcsound/data/` directly. Edit them in
`~/dev/csound/installer/`, then copy both files into `libcsound/data/` so they
stay byte-identical (`test/check-installer-sync.py` checks this against the
published upstream scripts).

## Keep libcsound ignorant of tokens/CI

The `libcsound` Python package must not contain any GitHub-token or CI-specific
logic. Authentication for the automatic csound download is handled entirely by
the bundled installer scripts, which read the token from the environment.
