/** Calibre descriptions carry HTML; render a plain-text excerpt.
 *  Falls back to the raw string where DOMParser is unavailable (non-DOM contexts). */
export function plainText(html: string): string {
	if (typeof DOMParser === 'undefined') return html;
	return (new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '')
		.replace(/_{3,}/g, ' ') // collapse Calibre separator underscore runs
		.replace(/\s+/g, ' ')
		.trim();
}
