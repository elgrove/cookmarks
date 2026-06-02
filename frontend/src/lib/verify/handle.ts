import type { VerifyResult } from './types';

const RESULT_JSON_ID = 'verify-result-json';

let currentResult: VerifyResult | null = null;
let lastRunAll: VerifyResult[] = [];

function mirrorToDom(payload: unknown): void {
	if (typeof document === 'undefined') return;
	let el = document.getElementById(RESULT_JSON_ID);
	if (!el) {
		el = document.createElement('script');
		el.id = RESULT_JSON_ID;
		el.setAttribute('type', 'application/json');
		document.body.appendChild(el);
	}
	el.textContent = JSON.stringify(payload);
}

/** Record the result of the currently-viewed unit so an agent can scrape it
 *  from #verify-result-json without evaluating JavaScript. */
export function setCurrent(result: VerifyResult | null): void {
	currentResult = result;
	mirrorToDom(result);
}

export function installVerifyHandle(): void {
	if (typeof window === 'undefined') return;
	// Load the runner — and through it the registry, which eagerly globs every
	// *.verify.ts and its component — only when verification is actually invoked.
	// The layout installs this handle on every page, so a static import would pull
	// the whole harness onto the critical path of normal pages (and into the prod
	// bundle); the dynamic import keeps it code-split until it's needed.
	window.__verify = {
		version: '2.0',
		manifest: async () => (await import('./runner')).buildManifest(),
		current: () => currentResult,
		runAll: async () => {
			const { runAll } = await import('./runner');
			lastRunAll = await runAll();
			mirrorToDom(lastRunAll);
			return lastRunAll;
		}
	};
}
