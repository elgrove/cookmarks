import ThemeToggle from '$lib/components/ThemeToggle.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Theme = 'light' | 'dark';
type Props = { theme: Theme; onToggle?: () => void };

const BTN = 'button.theme-toggle';

// A spy the click-probe asserts against; the probe's `act` resets it first so
// the count reflects only this run (the matrix may re-run a fixture).
let toggleCalls = 0;
const spy = () => {
	toggleCalls += 1;
};
const noop = () => {};

const unit: VerifiableUnit<Props> = {
	id: 'theme-toggle',
	title: 'Theme toggle',
	description:
		'The top-right light/dark switch — a controlled, presentational button whose icon and accessible name reflect the active theme.',
	kind: 'component',
	component: ThemeToggle,
	propsSchema: z.object({ theme: z.enum(['light', 'dark']) }),
	fixtures: [
		{
			id: 'light',
			description: 'light active — shows the sun, offers to switch to dark',
			props: { theme: 'light', onToggle: noop }
		},
		{
			id: 'dark',
			description: 'dark active — shows the moon, offers to switch to light',
			props: { theme: 'dark', onToggle: noop }
		},
		{
			id: 'rapid-toggle',
			description: 'probe: hammering the button fires onToggle each time without drifting the controlled icon',
			probe: true,
			props: { theme: 'light', onToggle: spy },
			act: ({ click }) => {
				toggleCalls = 0;
				click(BTN);
				click(BTN);
				click(BTN);
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { theme: 'light', onToggle: noop }
		}
	],
	invariants: [
		{
			id: 'reflects-theme',
			description: 'the DOM contract and accessible name match the active theme',
			onlyFixtures: ['light', 'dark'],
			check: ({ contract, props, root }) => {
				if (contract.theme !== props.theme)
					return `contract theme=${contract.theme}, prop=${props.theme}`;
				const label = root.querySelector(BTN)?.getAttribute('aria-label') ?? '';
				const wantsDark = props.theme === 'light';
				return (
					(wantsDark ? label.includes('dark') : label.includes('light')) ||
					`aria-label "${label}" doesn't match theme ${props.theme}`
				);
			}
		},
		{
			id: 'pressed-when-dark',
			description: 'aria-pressed tracks whether dark is the active theme',
			onlyFixtures: ['light', 'dark'],
			check: ({ props, root }) => {
				const pressed = root.querySelector(BTN)?.getAttribute('aria-pressed');
				return pressed === String(props.theme === 'dark') || `aria-pressed=${pressed}`;
			}
		},
		{
			id: 'fires-onToggle',
			description: 'each click calls onToggle; the controlled icon does not drift',
			onlyFixtures: ['rapid-toggle'],
			check: ({ contract, root }) => {
				if (toggleCalls !== 3) return `onToggle fired ${toggleCalls}× (expected 3)`;
				if (contract.theme !== 'light') return `theme drifted to ${contract.theme}`;
				return root.querySelector(BTN) !== null || 'toggle button vanished';
			}
		},
		{
			id: 'intentional-fail',
			description: 'always fails — the truthfulness sentinel (expectFail)',
			onlyFixtures: ['contract-lie'],
			check: () => 'intentional failure: this sentinel must surface as FAIL'
		}
	]
};

export default unit;
