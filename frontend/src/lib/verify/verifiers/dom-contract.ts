import type { Check, Verifier } from '../types';

/** Asserts the unit is self-identifying: a data-verify-unit matching the unit id. */
export const domContract: Verifier = {
	id: 'dom-contract',
	description: 'Unit exposes a data-verify-* contract identifying itself',
	run({ unit, contract }): Check[] {
		if (!contract.unit) {
			return [
				{
					verifier: 'dom-contract',
					status: 'fail',
					label: 'missing data-verify-unit',
					detail: `unit "${unit.id}" rendered no [data-verify-unit] element`
				}
			];
		}
		if (contract.unit !== unit.id) {
			return [
				{
					verifier: 'dom-contract',
					status: 'fail',
					label: 'contract identity mismatch',
					detail: `data-verify-unit="${contract.unit}" != unit id "${unit.id}"`
				}
			];
		}
		return [{ verifier: 'dom-contract', status: 'ok', label: `identifies as "${unit.id}"` }];
	}
};
