# Vendored: foliate-js

Pure-ESM e-book rendering engine (the engine behind the Foliate reader). Used here to render
EPUBs in the browser (`$lib/components/EpubReader.svelte`).

- **Source:** https://github.com/johnfactotum/foliate-js
- **Commit:** `78914aef4466eb960965702401634c2cb348e9b1`
- **Licence:** MIT (see `LICENSE`). Vendored sub-libs: zip.js (BSD-3-Clause), fflate (MIT).

## Why vendored (not a submodule)

foliate-js is not published on npm and upstream recommends a git submodule. We vendor a pinned copy
instead because this project develops in git **worktrees**, where submodules are awkward, and a
committed copy needs no `submodule update --init` step in dev/CI. To update: re-copy from a newer
upstream commit and bump the SHA above.

## Deviations from upstream

- **`pdf.js` is replaced with a stub.** Upstream `pdf.js` statically imports `vendor/pdfjs/`
  (~11 MB). This app reads **EPUB only**, and `view.js` imports `pdf.js` solely for files that
  sniff as PDF — never for EPUBs — so the stub throws if ever reached. `vendor/pdfjs/` is omitted.
- The demo (`reader.js`, `reader.html`, `ui/`) and build tooling (`rollup*`, `eslint.config.js`,
  `package*.json`, `tests/`) are not vendored — we ship our own Svelte reader UI.

Everything else is an unmodified copy. Do not hand-edit the vendored modules.
