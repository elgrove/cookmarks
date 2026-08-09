import SelectionBar, { type SelectionBarProps } from '$lib/components/SelectionBar.svelte';
import type { ListMembership } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = SelectionBarProps;

const ADD_BTN = '.add-btn';
const ROW = '.lists .list-toggle';
const CREATE_INPUT = '.create-input';
const CREATE_BTN = '.create-btn';
const REMOVE = '.bulk-remove';

function membership(over: Partial<ListMembership> = {}): ListMembership {
	return {
		id: over.id ?? 'l1',
		name: over.name ?? 'A list',
		is_default: over.is_default ?? false,
		contains: over.contains ?? false
	};
}

const LISTS: ListMembership[] = [
	membership({ id: 'fav', name: 'Favourites', is_default: true, contains: true }),
	membership({ id: 'wk', name: 'Weeknight', contains: false }),
	membership({ id: 'tt', name: 'To try', contains: true })
];

function props(extra: Partial<Props> = {}): Props {
	return { count: 2, total: 5, allSelected: false, lists: LISTS, ...extra };
}

const unit: VerifiableUnit<Props> = {
	id: 'selection-bar',
	title: 'Selection bar',
	description:
		'The sticky bar shown while a recipe surface is in select mode: a live selection count, select-all / clear, an add-to-list disclosure (with create), and — on list detail — a bulk remove.',
	kind: 'component',
	component: SelectionBar,
	propsSchema: z.object({
		count: z.number().int().nonnegative(),
		total: z.number().int().nonnegative(),
		allSelected: z.boolean(),
		lists: z.array(
			z.object({
				id: z.string(),
				name: z.string(),
				is_default: z.boolean(),
				contains: z.boolean()
			})
		)
	}),
	fixtures: [
		{
			id: 'some-selected',
			description: 'a partial selection: count, select-all and the add disclosure',
			props: props()
		},
		{
			id: 'all-selected',
			description: 'everything on the page selected — select-all disabled',
			props: props({ count: 5, allSelected: true })
		},
		{
			id: 'with-remove',
			description: 'the list-detail shape: a destructive bulk remove beside the add',
			props: props({ onRemove: () => {}, removeLabel: 'Remove from this list' }),
			act: ({ click }) => click(REMOVE)
		},
		{
			id: 'add-via-picker',
			description: 'opening the disclosure and clicking a list fires the add for that list',
			props: props(),
			act: ({ click }) => {
				click(ADD_BTN);
				click(`.lists li:nth-child(2) .list-toggle`);
			}
		},
		{
			id: 'create-from-selection',
			description: 'creating a list from the bar fires the create handler',
			props: props(),
			act: ({ click, type }) => {
				click(ADD_BTN);
				type(CREATE_INPUT, 'Sunday lunch');
				click(CREATE_BTN);
			}
		},
		{
			id: 'clear',
			description: 'clearing empties the selection and closes the panel',
			props: props(),
			act: ({ click }) => {
				click(ADD_BTN);
				click('.clear-sel');
			}
		},
		{
			id: 'empty-selection',
			description:
				'probe: count 0 / total 0 — the bar must not claim a selection or offer a destructive action',
			probe: true,
			props: props({ count: 0, total: 0, onRemove: () => {} })
		},
		{
			id: 'big-count',
			description: 'probe: a four-digit selection count renders without breaking the bar',
			probe: true,
			props: props({ count: 1234, total: 5678 })
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: props()
		}
	],
	invariants: [
		{
			id: 'count-live',
			description: 'the selection count reads out of an aria-live region',
			check: ({ contract, root, props }) => {
				const live = root.querySelector('[aria-live="polite"]');
				if (!live) return 'no aria-live region';
				if (!(live.textContent ?? '').includes(`${props.count} selected`))
					return `live region says "${live.textContent?.trim()}"`;
				return contract.count === String(props.count) || `count=${contract.count}`;
			}
		},
		{
			id: 'select-all-state',
			description: 'select-all names the page total and disables once everything is selected',
			check: ({ root, props }) => {
				const btn = root.querySelector<HTMLButtonElement>('.select-all');
				if (!btn) return 'select-all missing';
				if (!(btn.textContent ?? '').includes(String(props.total)))
					return `select-all label="${btn.textContent?.trim()}"`;
				const wantDisabled = props.allSelected || props.total === 0;
				return btn.disabled === wantDisabled || `select-all disabled=${btn.disabled}`;
			}
		},
		{
			id: 'add-wires',
			description: 'clicking a list in the disclosure echoes the add; ticks are suppressed',
			onlyFixtures: ['add-via-picker'],
			check: ({ contract, root }) => {
				if (contract.added !== 'Weeknight') return `added=${contract.added}`;
				const pressed = [...root.querySelectorAll(ROW)].filter(
					(r) => r.getAttribute('aria-pressed') === 'true'
				);
				return pressed.length === 0 || 'membership ticks must be suppressed in the bar';
			}
		},
		{
			id: 'create-wires',
			description: 'creating from the bar echoes the typed name',
			onlyFixtures: ['create-from-selection'],
			check: ({ contract }) =>
				contract.created === 'Sunday lunch' || `created=${contract.created}`
		},
		{
			id: 'remove-wires',
			description: 'the destructive action renders only when supplied, with its label, and wires',
			onlyFixtures: ['with-remove'],
			check: ({ contract, root }) => {
				const btn = root.querySelector(REMOVE);
				if (!btn) return 'bulk remove missing';
				if (!(btn.textContent ?? '').includes('Remove from this list'))
					return `remove label="${btn.textContent?.trim()}"`;
				return contract.removed === 'true' || `removed=${contract.removed}`;
			}
		},
		{
			id: 'no-remove-by-default',
			description: 'without an onRemove there is no destructive action at all',
			onlyFixtures: ['some-selected', 'all-selected', 'big-count'],
			check: ({ root }) =>
				root.querySelector(REMOVE) === null || 'bulk remove rendered without a handler'
		},
		{
			id: 'clear-wires',
			description: 'clearing echoes into the contract and closes the panel',
			onlyFixtures: ['clear'],
			check: ({ contract, root }) => {
				if (contract.cleared !== 'true') return `cleared=${contract.cleared}`;
				return root.querySelector('.panel') === null || 'panel still open after clear';
			}
		},
		{
			id: 'empty-offers-nothing',
			description: 'with nothing selected, add / clear / remove are all disabled',
			onlyFixtures: ['empty-selection'],
			check: ({ root }) => {
				for (const sel of [ADD_BTN, '.clear-sel', REMOVE, '.select-all']) {
					const btn = root.querySelector<HTMLButtonElement>(sel);
					if (btn && !btn.disabled) return `${sel} is live with an empty selection`;
				}
				return true;
			}
		},
		{
			id: 'big-count-renders',
			description: 'a four-digit count still reads correctly',
			onlyFixtures: ['big-count'],
			check: ({ root }) =>
				(root.textContent ?? '').includes('1234 selected') || 'count not rendered'
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
