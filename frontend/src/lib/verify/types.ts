import type { Component } from 'svelte';
import type { ZodType } from 'zod';

export type Verdict = 'PASS' | 'FAIL' | 'BLOCKED' | 'SKIP';

/** A non-fatal `warn` keeps a verdict at PASS; a `fail` drops it to FAIL. */
export type CheckStatus = 'ok' | 'fail' | 'warn';

export interface Check {
	verifier: string;
	status: CheckStatus;
	label: string;
	detail?: string;
}

export interface VerifyResult {
	unitId: string;
	fixtureId: string;
	verdict: Verdict;
	checks: Check[];
	contract: Record<string, string>;
	durationMs: number;
	blockedReason?: string;
}

export interface ActContext {
	root: HTMLElement;
	click: (selector: string) => void;
	type: (selector: string, text: string) => void;
	wait: (ms: number) => Promise<void>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface Fixture<P = any> {
	id: string;
	description: string;
	props: P;
	/** Marks an adversarial / edge-case fixture in the manifest. Does not change verdict logic. */
	probe?: boolean;
	act?: (ctx: ActContext) => void | Promise<void>;
}

export interface InvariantContext<P> {
	root: HTMLElement;
	props: P;
	fixture: Fixture<P>;
	contract: Record<string, string>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface Invariant<P = any> {
	id: string;
	description: string;
	/** Return true to pass, or a string describing the violation to fail. */
	check: (ctx: InvariantContext<P>) => boolean | string;
	onlyFixtures?: string[];
}

export interface VerifierContext {
	unit: VerifiableUnit;
	fixture: Fixture;
	root: HTMLElement;
	contract: Record<string, string>;
}

export interface Verifier {
	id: string;
	description: string;
	run: (ctx: VerifierContext) => Check[] | Promise<Check[]>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface VerifiableUnit<P extends Record<string, any> = Record<string, any>> {
	id: string;
	title: string;
	description?: string;
	kind: 'component' | 'feature';
	component: Component<P>;
	propsSchema?: ZodType;
	fixtures: Fixture<P>[];
	invariants?: Invariant<P>[];
	/** Restrict to a subset of verifier ids; defaults to all registered verifiers. */
	verifiers?: string[];
}

export interface ManifestEntry {
	unitId: string;
	fixtureId: string;
	probe: boolean;
	verifiers: string[];
}

export interface VerifyHandle {
	manifest: () => ManifestEntry[];
	current: () => VerifyResult | null;
	runAll: () => Promise<VerifyResult[]>;
	version: string;
}
