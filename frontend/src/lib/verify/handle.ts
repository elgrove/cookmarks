import { buildManifest, runAll } from './runner';
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
	window.__verify = {
		version: '2.0',
		manifest: buildManifest,
		current: () => currentResult,
		runAll: async () => {
			lastRunAll = await runAll();
			mirrorToDom(lastRunAll);
			return lastRunAll;
		}
	};
}
