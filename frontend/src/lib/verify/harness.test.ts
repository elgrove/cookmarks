import { describe, expect, it } from 'vitest';
import { runOne } from './runner';

// Proves the harness reports truthfully rather than going silently green:
// a consistent fixture PASSes, a deliberately broken one FAILs.
describe('harness self-test (smoke unit)', () => {
	it('passes the consistent fixture', async () => {
		const result = await runOne('smoke', 'ok');
		expect(result?.verdict).toBe('PASS');
	});

	it('catches the broken probe', async () => {
		const result = await runOne('smoke', 'broken');
		expect(result?.verdict).toBe('FAIL');
		expect(
			result?.checks.some((c) => c.verifier === 'invariants' && c.status === 'fail')
		).toBe(true);
	});
});
