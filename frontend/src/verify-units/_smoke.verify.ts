import Smoke from '$lib/components/Smoke.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

// Harness self-test. The `ok` fixture should PASS every verifier; the `broken`
// probe deliberately violates an invariant so the matrix shows a real FAIL,
// proving the harness reports truthfully. Delete once a real unit exists.
const unit: VerifiableUnit<{ label?: string; broken?: boolean }> = {
	id: 'smoke',
	title: 'Smoke (harness self-test)',
	description: 'Placeholder unit that proves the verification loop catches lies.',
	kind: 'component',
	component: Smoke,
	propsSchema: z.object({ label: z.string().optional(), broken: z.boolean().optional() }),
	fixtures: [
		{ id: 'ok', description: 'consistent count of 1', props: { label: 'hello' } },
		{
			id: 'broken',
			description: 'probe: count contradicts the invariant',
			props: { broken: true },
			probe: true
		}
	],
	invariants: [
		{
			id: 'count-is-one',
			description: 'the rendered count contract equals 1',
			check: ({ contract }) =>
				contract.count === '1' || `expected count=1, saw count=${contract.count}`
		}
	]
};

export default unit;
