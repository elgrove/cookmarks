import type { Verifier } from '../types';
import { a11y } from './a11y';
import { domContract } from './dom-contract';
import { invariants } from './invariants';
import { schema } from './schema';

// Pluggable: add a verifier file and append it here — no component changes needed.
export const verifiers: Verifier[] = [domContract, schema, invariants, a11y];
