# pdfjs

Mozilla pdf.js (Apache-2.0), vendored by foliate-js and served from here rather than from
beside its loader: `cmaps/` and `standard_fonts/` are whole directories fetched by URL at
runtime, which a bundler cannot emit out of `src/`.

Provenance, version and the deviations from upstream are recorded in
`../../src/lib/vendor/foliate-js/PROVENANCE.md`. Do not hand-edit these files.
