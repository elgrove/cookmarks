const PREFIX = 'data-verify-';

/**
 * Read the data-verify-* DOM contract off the first self-identifying element
 * (the one carrying data-verify-unit). Returns a flat record keyed without the
 * prefix, e.g. `data-verify-count="3"` -> `{ unit: "...", count: "3" }`.
 */
export function readContract(root: HTMLElement): Record<string, string> {
	const el = root.querySelector<HTMLElement>(`[${PREFIX}unit]`);
	const out: Record<string, string> = {};
	if (!el) return out;
	for (const attr of Array.from(el.attributes)) {
		if (attr.name.startsWith(PREFIX)) {
			out[attr.name.slice(PREFIX.length)] = attr.value;
		}
	}
	return out;
}
