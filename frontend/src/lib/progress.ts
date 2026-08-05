/** Share of a book's recipes seen, 0–100 — or null when there is nothing extracted
 *  yet, so an unextracted book shows no percentage rather than NaN. A stale count
 *  above the total clamps to 100 instead of overflowing. */
export function readPercent(seen: number, total: number): number | null {
	if (total <= 0) return null;
	return Math.max(0, Math.min(100, Math.round((100 * seen) / total)));
}
