/** Document title pattern: brand first, middot separator (e.g. "Cookmarks · Recipes").
 *  Bare "Cookmarks" on the home page; `section` carries a page name or entity title. */
export function pageTitle(section?: string | null): string {
	const trimmed = section?.trim();
	return trimmed ? `Cookmarks · ${trimmed}` : 'Cookmarks';
}

/** Calibre titles pack a subtitle behind a colon (e.g. "Persiana: Recipes from…").
 *  The clean title is the part before the first colon. */
export function cleanTitle(title: string): string {
	const i = title.indexOf(':');
	return i === -1 ? title : title.slice(0, i).trim();
}

/** The remainder after the first colon, with any further colons softened to em-dashes. */
export function titleSubtitle(title: string): string {
	const i = title.indexOf(':');
	return i === -1
		? ''
		: title
				.slice(i + 1)
				.replace(/\s*:\s*/g, ' — ')
				.trim();
}
