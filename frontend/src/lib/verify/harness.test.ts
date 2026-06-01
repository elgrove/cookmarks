import { describe, expect, it } from 'vitest';
import { runOne } from './runner';

// Proves the harness reports truthfully rather than going silently green:
// a consistent fixture PASSes, a deliberately broken one FAILs via an invariant.
describe('harness self-test (books-library unit)', () => {
	it('passes the consistent fixture', async () => {
		const result = await runOne('books-library', 'populated');
		expect(result?.verdict).toBe('PASS');
	});

	it('catches the expectFail sentinel', async () => {
		const result = await runOne('books-library', 'contract-lie');
		expect(result?.verdict).toBe('FAIL');
		expect(
			result?.checks.some((c) => c.verifier === 'invariants' && c.status === 'fail')
		).toBe(true);
	});
});
