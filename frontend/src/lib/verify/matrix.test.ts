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

			it('passes all non-probe fixtures', async () => {
				const results = await runUnit(unit);
				const regressions = results
					.filter((r) => !unit.fixtures.find((f) => f.id === r.fixtureId)?.probe)
					.filter((r) => r.verdict !== 'PASS')
					.map((r) => `${r.unitId}/${r.fixtureId}=${r.verdict}`);
				expect(regressions).toEqual([]);
			});
		});
	}
});
