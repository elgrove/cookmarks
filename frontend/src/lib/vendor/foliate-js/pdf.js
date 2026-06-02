// EPUB-only build: PDF rendering is intentionally omitted (pdfjs is ~11MB and never
// invoked for EPUBs). view.js only imports this for files that sniff as PDF.
export const makePDF = () => {
    throw new Error('PDF rendering is not supported in this build')
}
