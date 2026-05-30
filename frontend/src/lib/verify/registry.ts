import type { VerifiableUnit, Verifier } from './types';
import { verifiers as builtinVerifiers } from './verifiers';

// Drop a `*.verify.ts` file anywhere under src/ that default-exports a
// VerifiableUnit and it registers automatically — co-locate specs with units.
const modules = import.meta.glob<{ default: VerifiableUnit }>('/src/**/*.verify.ts', {
	eager: true
});

export const units: VerifiableUnit[] = Object.values(modules)
	.map((m) => m.default)
	.filter((u): u is VerifiableUnit => Boolean(u))
	.sort((a, b) => a.id.localeCompare(b.id));

export const verifiers: Verifier[] = builtinVerifiers;

export function getUnit(id: string): VerifiableUnit | undefined {
	return units.find((u) => u.id === id);
}

export function verifiersFor(unit: VerifiableUnit): Verifier[] {
	if (!unit.verifiers) return verifiers;
	return verifiers.filter((v) => unit.verifiers?.includes(v.id));
}
