import { describe, expect, it } from 'vitest';
import { units } from './registry';
import { runUnit } from './runner';
import type { Verdict } from './types';

const TAXONOMY: Verdict[] = ['PASS', 'FAIL', 'BLOCKED', 'SKIP'];

describe('verify matrix', () => {
	it('registers at least one unit', () => {
		expect(units.length).toBeGreaterThan(0);
	});

	for (const unit of units) {
		describe(unit.id, () => {
			it('declares at least one probe fixture', () => {
				expect(unit.fixtures.some((f) => f.probe)).toBe(true);
			});

			it('yields a taxonomy verdict for every fixture', async () => {
				const results = await runUnit(unit);
				for (const r of results) expect(TAXONOMY).toContain(r.verdict);
			});

			// Probes are adversarial inputs that must still PASS; only fixtures explicitly
			// marked expectFail are allowed (and required) to FAIL.
			it('passes every fixture that is not an expectFail sentinel', async () => {
				const results = await runUnit(unit);
				const regressions = results
					.filter((r) => !unit.fixtures.find((f) => f.id === r.fixtureId)?.expectFail)
					.filter((r) => r.verdict !== 'PASS')
					.map((r) => `${r.unitId}/${r.fixtureId}=${r.verdict}`);
				expect(regressions).toEqual([]);
			});

			it('fails every expectFail sentinel (proves the harness reports truthfully)', async () => {
				const results = await runUnit(unit);
				const wrong = results
					.filter((r) => unit.fixtures.find((f) => f.id === r.fixtureId)?.expectFail)
					.filter((r) => r.verdict !== 'FAIL')
					.map((r) => `${r.unitId}/${r.fixtureId}=${r.verdict}`);
				expect(wrong).toEqual([]);
			});
		});
	}
});
