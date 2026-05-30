import type { Check, Verifier } from '../types';

/** Validates fixture props against the unit's optional Zod schema. */
export const schema: Verifier = {
	id: 'schema',
	description: 'Fixture props conform to the declared schema',
	run({ unit, fixture }): Check[] {
		if (!unit.propsSchema) {
			return [{ verifier: 'schema', status: 'warn', label: 'no propsSchema declared' }];
		}
		const result = unit.propsSchema.safeParse(fixture.props);
		if (result.success) {
			return [{ verifier: 'schema', status: 'ok', label: 'props valid' }];
		}
		return [
			{
				verifier: 'schema',
				status: 'fail',
				label: 'props invalid',
				detail: result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')
			}
		];
	}
};
