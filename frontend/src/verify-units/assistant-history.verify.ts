import AssistantHistory, {
	type AssistantHistoryProps
} from '$lib/components/AssistantHistory.svelte';
import type { ConversationSummary } from '$lib/api/assistant';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = AssistantHistoryProps;

function conversation(over: Partial<ConversationSummary> = {}): ConversationSummary {
	return {
		id: over.id ?? 'c1',
		title: over.title === undefined ? 'Something warming with lentils' : over.title,
		created_at: over.created_at ?? '2026-08-26T19:04:11Z',
		updated_at: over.updated_at ?? '2026-08-26T19:06:48Z'
	};
}

const conversations: ConversationSummary[] = [
	conversation({ id: 'c1' }),
	conversation({ id: 'c2', title: 'What to do with a glut of fennel' }),
	conversation({ id: 'c3', title: null })
];

const NEW = '.new';
const OPEN = '.open';
const REMOVE = '.remove';

const unit: VerifiableUnit<Props> = {
	id: 'assistant-history',
	title: 'Assistant history',
	description:
		'The rail of past conversations: pick one up, start a new one, or throw one away. Newest first, the open one marked.',
	kind: 'component',
	component: AssistantHistory,
	fixtures: [
		{
			id: 'populated',
			description: 'three past conversations, the first one open',
			props: { conversations, activeId: 'c1' }
		},
		{
			id: 'empty',
			description: 'a fresh account — nothing asked yet',
			props: { conversations: [] }
		},
		{
			id: 'select',
			description: 'clicking a conversation asks for it to be opened',
			props: { conversations, activeId: 'c1' },
			act: ({ click }) => click(`.item:nth-child(2) ${OPEN}`)
		},
		{
			id: 'new-chat',
			description: 'the New button starts a fresh conversation',
			props: { conversations, activeId: 'c1' },
			act: ({ click }) => click(NEW)
		},
		{
			id: 'delete',
			description: 'the × throws a conversation away',
			props: { conversations, activeId: 'c1' },
			act: ({ click }) => click(REMOVE)
		},
		{
			id: 'overlong-titles',
			description: 'probe: untitled and absurdly long unicode titles all render as one row each',
			probe: true,
			props: {
				conversations: Array.from({ length: 8 }, (_, i) =>
					conversation({
						id: `x${i}`,
						title: i % 3 === 0 ? null : `Très long — ${i} — 你好 ${'noodles '.repeat(20)}`
					})
				),
				activeId: 'x0'
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { conversations, activeId: 'c1' }
		}
	],
	invariants: [
		{
			id: 'rows-rendered',
			description: 'every conversation gets a row, the open one marked current',
			onlyFixtures: ['populated'],
			check: ({ contract, root, props }) => {
				const rows = root.querySelectorAll('.item');
				if (rows.length !== props.conversations.length)
					return `expected ${props.conversations.length} rows, saw ${rows.length}`;
				if (contract.count !== String(props.conversations.length))
					return `count=${contract.count}`;
				if (contract.active !== 'c1') return `active=${contract.active}`;
				const current = root.querySelectorAll('[aria-current="true"]');
				return current.length === 1 || `${current.length} rows marked current`;
			}
		},
		{
			id: 'untitled-is-named',
			description: 'a conversation with no title still reads as something, never blank',
			onlyFixtures: ['populated'],
			check: ({ root }) => {
				const labels = [...root.querySelectorAll('.open')].map((b) => b.textContent?.trim() ?? '');
				if (labels.some((l) => l === '')) return 'a row rendered with no label';
				return labels.includes('Untitled') || `labels=${labels.join('|')}`;
			}
		},
		{
			id: 'empty-state',
			description: 'no conversations shows the calm empty line and no rows',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.item')) return 'no rows expected';
				return (root.textContent ?? '').includes('Nothing asked yet') || 'empty message missing';
			}
		},
		{
			id: 'new-is-always-offered',
			description: 'starting a new conversation is reachable from every state',
			check: ({ root }) => root.querySelector('.new') !== null || 'no New button'
		},
		{
			id: 'delete-wires',
			description: 'deleting the first conversation records its id',
			onlyFixtures: ['delete'],
			check: ({ contract }) => contract.deleted === 'c1' || `deleted=${contract.deleted}`
		},
		{
			id: 'overlong-titles-render',
			description: 'every overlong or absent title still renders exactly one row',
			onlyFixtures: ['overlong-titles'],
			check: ({ root, props }) => {
				const rows = root.querySelectorAll('.item');
				return rows.length === props.conversations.length || `saw ${rows.length} rows`;
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
