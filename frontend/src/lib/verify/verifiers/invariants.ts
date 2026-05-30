import type { Check, Verifier } from '../types';

/** Runs the unit's declared invariants against the mounted DOM + contract. */
export const invariants: Verifier = {
	id: 'invariants',
	description: 'Declared invariants hold for the mounted fixture',
	run({ unit, fixture, root, contract }): Check[] {
		const declared = unit.invariants ?? [];
		const applicable = declared.filter(
			(inv) => !inv.onlyFixtures || inv.onlyFixtures.includes(fixture.id)
		);
		if (applicable.length === 0) {
			return [{ verifier: 'invariants', status: 'warn', label: 'no invariants declared' }];
		}
		return applicable.map((inv): Check => {
			const result = inv.check({ root, props: fixture.props, fixture, contract });
			if (result === true) {
				return { verifier: 'invariants', status: 'ok', label: inv.id };
			}
			return {
				verifier: 'invariants',
				status: 'fail',
				label: inv.id,
				detail: typeof result === 'string' ? result : inv.description
			};
		});
	}
};
