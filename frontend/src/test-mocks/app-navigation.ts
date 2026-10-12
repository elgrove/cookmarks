// Minimal $app/navigation stand-in for route tests under plain vitest.
export function goto(): Promise<void> {
	return Promise.resolve();
}
