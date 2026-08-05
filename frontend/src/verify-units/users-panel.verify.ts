import UsersPanel, { type UsersPanelProps } from '$lib/components/UsersPanel.svelte';
import type { User } from '$lib/api/auth';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = UsersPanelProps;

const user = (over: Partial<User> = {}): User => ({
	id: 'a1b2c3d4-0000-4000-8000-000000000001',
	username: 'aaron',
	is_admin: true,
	created_at: '2026-06-05T10:00:00Z',
	...over
});

const SEVERAL: User[] = [
	user(),
	user({ id: 'a1b2c3d4-0000-4000-8000-000000000002', username: 'sam', is_admin: false }),
	user({
		id: 'a1b2c3d4-0000-4000-8000-000000000003',
		username: 'jo',
		is_admin: false,
		created_at: '2026-07-01T09:30:00Z'
	})
];

const NAME = '#new-username';
const PASSWORD = '#new-password';
const CREATE = '.submit';

const rows = (root: HTMLElement): number => root.querySelectorAll('tbody tr').length;

const unit: VerifiableUnit<Props> = {
	id: 'users-panel',
	title: 'Users panel',
	description:
		'The admin Users tab: every account with its role and date, a create form, and per-row delete and password reset. Delete is disabled — with an accessible reason — for the last admin and for your own row.',
	kind: 'component',
	component: UsersPanel,
	fixtures: [
		{
			id: 'several',
			description: 'three accounts, one admin — the ordinary state',
			props: { users: SEVERAL, currentUserId: SEVERAL[1].id }
		},
		{
			id: 'sole-admin',
			description: 'a single admin: delete is disabled and says why',
			props: { users: [user()] }
		},
		{
			id: 'create-duplicate',
			description: 'probe: a rejected create (duplicate username) surfaces the error, adds no row',
			probe: true,
			props: {
				users: SEVERAL,
				onCreate: () => Promise.reject(new Error('that username is already taken'))
			},
			act: async ({ type, click, wait }) => {
				type(NAME, 'aaron');
				type(PASSWORD, 'hunter2');
				click(CREATE);
				await wait(0);
			}
		},
		{
			id: 'empty',
			description: 'probe: no accounts at all still renders a usable create form',
			probe: true,
			props: { users: [] }
		},
		{
			id: 'long-username',
			description: 'probe: an absurdly long username still renders exactly one row',
			probe: true,
			props: { users: [user({ username: 'a'.repeat(120) })] }
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { users: SEVERAL }
		}
	],
	invariants: [
		{
			id: 'count-matches-rows',
			description: 'the reported user count equals the number of rendered rows',
			check: ({ contract, root }) =>
				contract['user-count'] === String(rows(root)) ||
				`user-count=${contract['user-count']} rows=${rows(root)}`
		},
		{
			id: 'create-form-always-present',
			description: 'the create form is reachable whatever the account list looks like',
			check: ({ root }) =>
				(root.querySelector(NAME) !== null && root.querySelector(PASSWORD) !== null) ||
				'create form missing'
		},
		{
			id: 'sole-admin-delete-disabled',
			description: 'the last admin cannot be deleted, and the control says why',
			onlyFixtures: ['sole-admin'],
			check: ({ root }) => {
				const del = root.querySelector<HTMLButtonElement>('.delete');
				if (!del) return 'no delete control';
				if (!del.disabled) return 'the last admin can be deleted';
				const reason = del.getAttribute('aria-label') ?? '';
				return reason.includes('last admin') || `no accessible reason: "${reason}"`;
			}
		},
		{
			id: 'own-row-not-deletable',
			description: 'your own account offers no delete',
			onlyFixtures: ['several'],
			check: ({ root, props }) => {
				const row = root.querySelector(`tr[data-user-id="${props.currentUserId}"]`);
				const del = row?.querySelector<HTMLButtonElement>('.delete');
				if (!del) return 'no delete control on own row';
				return del.disabled || 'own account is deletable';
			}
		},
		{
			id: 'duplicate-surfaces-error',
			description: 'a rejected create shows the backend message and adds no row',
			onlyFixtures: ['create-duplicate'],
			check: ({ contract, root }) => {
				if (contract.error !== 'that username is already taken')
					return `error=${contract.error}`;
				return rows(root) === SEVERAL.length || `rows=${rows(root)}`;
			}
		},
		{
			id: 'empty-has-no-rows',
			description: 'an empty account list renders no rows and reports zero',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (rows(root) !== 0) return `rows=${rows(root)}`;
				return contract['user-count'] === '0' || `user-count=${contract['user-count']}`;
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
