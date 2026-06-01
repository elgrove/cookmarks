import { flushSync, mount, unmount } from 'svelte';
import { readContract } from './contract';
import { getUnit, units, verifiersFor } from './registry';
import type {
	ActContext,
	Check,
	Fixture,
	ManifestEntry,
	Verdict,
	VerifiableUnit,
	VerifyResult
} from './types';

function verdictOf(checks: Check[]): Verdict {
	return checks.some((c) => c.status === 'fail') ? 'FAIL' : 'PASS';
}

function makeActContext(root: HTMLElement): ActContext {
	return {
		root,
		click(selector) {
			root.querySelector<HTMLElement>(selector)?.click();
			flushSync();
		},
		type(selector, text) {
			const el = root.querySelector<HTMLInputElement>(selector);
			if (el) {
				el.value = text;
				el.dispatchEvent(new Event('input', { bubbles: true }));
				flushSync();
			}
		},
		wait(ms) {
			return new Promise((resolve) => setTimeout(resolve, ms));
		}
	};
}

export interface RunOptions {
	/** Mount into this element (left visible) instead of a hidden off-screen container.
	 *  The isolation route passes its on-screen node so the *verified* instance is the
	 *  one the agent screenshots — `act` and all. */
	target?: HTMLElement;
	/** Leave the component mounted after verifying (for the visible isolation route). */
	keepMounted?: boolean;
}

/** mount -> act -> verify -> verdict, for one unit/fixture pair. The single code
 *  path shared by the dashboard, the agent (window.__verify), the isolation route
 *  and CI — so the screenshot, the DOM contract and the verdict can never disagree. */
export async function runFixture(
	unit: VerifiableUnit,
	fixture: Fixture,
	opts: RunOptions = {}
): Promise<VerifyResult> {
	const start = performance.now();
	const ownsContainer = !opts.target;
	let container: HTMLElement;
	if (opts.target) {
		container = opts.target;
	} else {
		container = document.createElement('div');
		container.style.position = 'fixed';
		container.style.left = '-10000px';
		container.style.top = '0';
		document.body.appendChild(container);
	}

	const checks: Check[] = [];
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let instance: Record<string, any> | null = null;

	try {
		instance = mount(unit.component, { target: container, props: fixture.props });
		flushSync();

		if (fixture.act) await fixture.act(makeActContext(container));
		flushSync();

		const contract = readContract(container);

		for (const verifier of verifiersFor(unit)) {
			try {
				checks.push(...(await verifier.run({ unit, fixture, root: container, contract })));
			} catch (err) {
				checks.push({
					verifier: verifier.id,
					status: 'fail',
					label: 'verifier threw',
					detail: String(err)
				});
			}
		}

		return {
			unitId: unit.id,
			fixtureId: fixture.id,
			verdict: verdictOf(checks),
			checks,
			contract,
			durationMs: performance.now() - start
		};
	} catch (err) {
		return {
			unitId: unit.id,
			fixtureId: fixture.id,
			verdict: 'BLOCKED',
			checks,
			contract: {},
			durationMs: performance.now() - start,
			blockedReason: `mount failed: ${String(err)}`
		};
	} finally {
		if (!opts.keepMounted) {
			if (instance) {
				try {
					unmount(instance);
				} catch {
					/* best-effort teardown */
				}
			}
			if (ownsContainer) container.remove();
		}
	}
}

export async function runUnit(unit: VerifiableUnit): Promise<VerifyResult[]> {
	if (unit.fixtures.length === 0) {
		return [
			{
				unitId: unit.id,
				fixtureId: '(none)',
				verdict: 'SKIP',
				checks: [],
				contract: {},
				durationMs: 0,
				blockedReason: 'unit declares no fixtures'
			}
		];
	}
	const results: VerifyResult[] = [];
	for (const fixture of unit.fixtures) {
		results.push(await runFixture(unit, fixture));
	}
	return results;
}

export async function runAll(): Promise<VerifyResult[]> {
	const results: VerifyResult[] = [];
	for (const unit of units) {
		results.push(...(await runUnit(unit)));
	}
	return results;
}

export async function runOne(unitId: string, fixtureId: string): Promise<VerifyResult | null> {
	const unit = getUnit(unitId);
	const fixture = unit?.fixtures.find((f) => f.id === fixtureId);
	if (!unit || !fixture) return null;
	return runFixture(unit, fixture);
}

export function buildManifest(): ManifestEntry[] {
	return units.flatMap((unit) =>
		unit.fixtures.map((fixture) => ({
			unitId: unit.id,
			fixtureId: fixture.id,
			probe: Boolean(fixture.probe),
			expectFail: Boolean(fixture.expectFail),
			verifiers: verifiersFor(unit).map((v) => v.id)
		}))
	);
}
