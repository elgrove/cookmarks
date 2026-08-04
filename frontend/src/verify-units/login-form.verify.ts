import LoginForm, { type LoginFormProps } from '$lib/components/LoginForm.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = LoginFormProps;

const USER = '#login-username';
const PASS = '#login-password';
const SUBMIT = '.submit';

const unit: VerifiableUnit<Props> = {
	id: 'login-form',
	title: 'Login form',
	description:
		'The sign-in form: username, password, submit. Drives idle → submitting → error; a rejected login lands on the backend’s generic message and never a false success. Empty fields never reach the network.',
	kind: 'component',
	component: LoginForm,
	fixtures: [
		{
			id: 'resting',
			description: 'the empty form — nothing typed, submit disabled',
			props: {}
		},
		{
			id: 'submitting',
			description: 'credentials entered and submitted, the request still in flight',
			props: { onSubmit: () => new Promise<void>(() => {}) },
			act: async ({ type, click, wait }) => {
				type(USER, 'aaron');
				type(PASS, 'hunter2');
				click(SUBMIT);
				await wait(0);
			}
		},
		{
			id: 'rejected',
			description: 'probe: rejected credentials settle on an error state, never a false success',
			probe: true,
			props: {
				onSubmit: () => Promise.reject(new Error('Incorrect username or password.'))
			},
			act: async ({ type, click, wait }) => {
				type(USER, 'aaron');
				type(PASS, 'wrong');
				click(SUBMIT);
				await wait(0);
			}
		},
		{
			id: 'empty-submit',
			description: 'probe: submitting with empty fields never calls onSubmit',
			probe: true,
			props: {
				onSubmit: () => {
					throw new Error('onSubmit fired with empty fields');
				}
			},
			act: async ({ click, wait }) => {
				click(SUBMIT);
				await wait(0);
			}
		},
		{
			id: 'whitespace-username',
			description: 'probe: a whitespace-only username counts as empty, so submit stays disabled',
			probe: true,
			props: {
				onSubmit: () => {
					throw new Error('onSubmit fired for a blank username');
				}
			},
			act: async ({ type, click, wait }) => {
				type(USER, '   ');
				type(PASS, 'hunter2');
				click(SUBMIT);
				await wait(0);
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: {}
		}
	],
	invariants: [
		{
			id: 'state-is-known',
			description: 'the reported state is one of idle | submitting | error',
			check: ({ contract }) =>
				['idle', 'submitting', 'error'].includes(contract.state) || `state=${contract.state}`
		},
		{
			id: 'error-iff-error-state',
			description: 'a message is present exactly when the state is error',
			check: ({ contract }) => {
				const hasError = (contract.error ?? '') !== '';
				if (contract.state === 'error') return hasError || 'error state carries no message';
				return !hasError || `message "${contract.error}" outside the error state`;
			}
		},
		{
			id: 'resting-idle',
			description: 'the untouched form is idle with submit disabled',
			onlyFixtures: ['resting'],
			check: ({ contract, root }) => {
				if (contract.state !== 'idle') return `state=${contract.state}`;
				const submit = root.querySelector<HTMLButtonElement>(SUBMIT);
				return submit?.disabled === true || 'submit is enabled on an empty form';
			}
		},
		{
			id: 'in-flight-submitting',
			description: 'a request in flight holds the submitting state',
			onlyFixtures: ['submitting'],
			check: ({ contract }) => contract.state === 'submitting' || `state=${contract.state}`
		},
		{
			id: 'rejection-errors',
			description: 'a rejected login lands on error, showing the backend’s message',
			onlyFixtures: ['rejected'],
			check: ({ contract }) => {
				if (contract.state !== 'error') return `state=${contract.state}`;
				return (
					contract.error === 'Incorrect username or password.' || `error=${contract.error}`
				);
			}
		},
		{
			id: 'empty-never-submits',
			description: 'an empty (or whitespace) form stays idle — onSubmit is never reached',
			onlyFixtures: ['empty-submit', 'whitespace-username'],
			check: ({ contract }) => contract.state === 'idle' || `state=${contract.state}`
		},
		{
			id: 'password-is-masked',
			description: 'the password control is a password input, never plain text',
			check: ({ root }) =>
				root.querySelector('input[type="password"]#login-password') !== null ||
				'password field is not masked'
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
