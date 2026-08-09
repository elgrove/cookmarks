import ListPanelBody, { type ListPanelBodyProps } from '$lib/components/ListPanelBody.svelte';
import type { ListMembership } from '$lib/api/lists';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = ListPanelBodyProps;

const ROW = '.lists .list-toggle';
const CREATE_INPUT = '.create-input';

function membership(over: Partial<ListMembership> = {}): ListMembership {
	return {
		id: over.id ?? 'l1',
		name: over.name ?? 'A list',
		is_default: over.is_default ?? false,
		contains: over.contains ?? false
	};
}

const MIXED: ListMembership[] = [
	membership({ id: 'fav', name: 'Favourites', is_default: true, contains: true }),
	membership({ id: 'wk', name: 'Weeknight dinners', contains: false }),
	membership({ id: 'tt', name: 'To try', contains: true })
];

const unit: VerifiableUnit<Props> = {
	id: 'list-panel-body',
	title: 'List panel body',
	description:
		'The shared innards of every list picker (recipe page, reader popover, row picker, selection bar): membership toggle rows with Favourites pinned first, an inline create field, and loading/error notes. Purely presentational — the shells own data and positioning.',
	kind: 'component',
	component: ListPanelBody,
	propsSchema: z.object({
		lists: z.array(
			z.object({
				id: z.string(),
				name: z.string(),
				is_default: z.boolean(),
				contains: z.boolean()
			})
		),
		phase: z.enum(['loading', 'ready', 'error']).optional(),
		busy: z.string().nullable().optional(),
		showCreate: z.boolean().optional()
	}),
	fixtures: [
		{
			id: 'ready',
			description: 'mixed membership, Favourites first, with the create field',
			props: { lists: MIXED }
		},
		{
			id: 'loading',
			description: 'the loading note — no rows, no create field yet',
			props: { lists: [], phase: 'loading' }
		},
		{
			id: 'error',
			description: 'the error note — no rows, no create field',
			props: { lists: [], phase: 'error' }
		},
		{
			id: 'no-create',
			description: 'showCreate: false renders the rows without the create field',
			props: { lists: MIXED, showCreate: false }
		},
		{
			id: 'busy',
			description: 'the row with an operation in flight is disabled',
			props: { lists: MIXED, busy: 'wk' }
		},
		{
			id: 'long-names',
			description: 'probe: eight overlong unicode names all render as labelled toggles',
			probe: true,
			props: {
				lists: Array.from({ length: 8 }, (_, i) =>
					membership({
						id: `x${i}`,
						name: `Très Long Collection Name Number ${i} — 你好 ${'spaghetti '.repeat(3)}`,
						is_default: i === 0,
						contains: i % 2 === 0
					})
				)
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { lists: MIXED }
		}
	],
	invariants: [
		{
			id: 'one-toggle-per-list',
			description: 'the ready phase renders exactly one aria-pressed button per list',
			check: ({ contract, root, props }) => {
				const want = (props.phase ?? 'ready') === 'ready' ? props.lists.length : 0;
				const rows = root.querySelectorAll(`${ROW}[aria-pressed]`).length;
				if (rows !== want) return `expected ${want} toggles, saw ${rows}`;
				return Number(contract.lists) === props.lists.length || `lists=${contract.lists}`;
			}
		},
		{
			id: 'default-first',
			description: 'a default list supplied first renders starred in the first row',
			check: ({ root, props }) => {
				if ((props.phase ?? 'ready') !== 'ready' || !props.lists[0]?.is_default) return true;
				return (
					root.querySelector('.lists li:first-child .star') !== null ||
					'first row missing its default star'
				);
			}
		},
		{
			id: 'phase-gates-rows',
			description: 'loading/error show only the note; ready shows only the rows',
			check: ({ contract, root }) => {
				const note = root.querySelector('.note') !== null;
				const rows = root.querySelector('.lists') !== null;
				if (contract.phase === 'ready') return (!note && rows) || 'ready must show rows, no note';
				return (note && !rows) || `${contract.phase} must show the note and no rows`;
			}
		},
		{
			id: 'create-gated',
			description: 'the create field renders only when showCreate and the phase is ready',
			check: ({ contract, root }) => {
				const has = root.querySelector(CREATE_INPUT) !== null;
				const want = contract.phase === 'ready' && contract.create === 'true';
				return has === want || `create field ${has ? 'rendered' : 'missing'} unexpectedly`;
			}
		},
		{
			id: 'busy-disables',
			description: 'the busy row is disabled; the others stay live',
			onlyFixtures: ['busy'],
			check: ({ root, props }) => {
				const rows = [...root.querySelectorAll<HTMLButtonElement>(ROW)];
				const busyIdx = props.lists.findIndex((l) => l.id === props.busy);
				if (!rows[busyIdx]?.disabled) return 'busy row is not disabled';
				const others = rows.filter((_, i) => i !== busyIdx);
				return others.every((r) => !r.disabled) || 'a non-busy row is disabled';
			}
		},
		{
			id: 'long-names-render',
			description: 'every overlong list still renders as a labelled toggle',
			onlyFixtures: ['long-names'],
			check: ({ root, props }) => {
				const rows = root.querySelectorAll(ROW);
				return (
					rows.length === props.lists.length ||
					`expected ${props.lists.length} toggles, saw ${rows.length}`
				);
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
