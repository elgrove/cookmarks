# Vendored: foliate-js

Pure-ESM e-book rendering engine (the engine behind the Foliate reader). Used here to render
EPUBs in the browser (`$lib/components/EpubReader.svelte`).

- **Source:** https://github.com/johnfactotum/foliate-js
- **Commit:** `78914aef4466eb960965702401634c2cb348e9b1`
- **Licence:** MIT (see `LICENSE`). Vendored sub-libs: zip.js (BSD-3-Clause), fflate (MIT),
  pdf.js (Apache-2.0, Mozilla — shipped from `frontend/static/pdfjs/`).

## Why vendored (not a submodule)

foliate-js is not published on npm and upstream recommends a git submodule. We vendor a pinned copy
instead because this project develops in git **worktrees**, where submodules are awkward, and a
committed copy needs no `submodule update --init` step in dev/CI. To update: re-copy from a newer
upstream commit and bump the SHA above.

## Deviations from upstream

- **`pdf.js` loads pdfjs from `frontend/static/pdfjs/`, not from beside itself.** Upstream resolves
  pdfjs against `import.meta.url`, and among the things it resolves are the whole `cmaps/` and
  `standard_fonts/` directories — which a bundler cannot emit out of `src/`. So `vendor/pdfjs/`
  lives under `static/` (copied verbatim, served at `/pdfjs/`) and the three-line preamble of
  `pdf.js` points at it, loading `pdf.mjs` by dynamic import instead of a bare static one. The
  rest of the module is upstream's. Consequence, and the reason for it: nothing of pdfjs is
  bundled at all — `view.js` imports `pdf.js` only for files that sniff as PDF, so an EPUB-only
  session never fetches a byte of it.
- **The pdfjs `*.map` source maps are not vendored** (7.7 MB of debug artefacts for a minified
  dependency we do not debug). `pdf.mjs` and `pdf.worker.mjs` still carry their
  `sourceMappingURL` comment, and the SPA catch-all answers the missing map with `index.html`,
  so devtools logs a parse error rather than a clean 404.
- **`build.target` is raised to `es2022`** in `vite.config.ts` — upstream `pdf.js` uses top-level
  await, which Vite's default target predates.
- The demo (`reader.js`, `reader.html`, `ui/`) and build tooling (`rollup*`, `eslint.config.js`,
  `package*.json`, `tests/`) are not vendored — we ship our own Svelte reader UI.

Everything else is an unmodified copy. Do not hand-edit the vendored modules.
