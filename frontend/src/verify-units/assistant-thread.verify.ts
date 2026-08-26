import AssistantThread, {
	type AssistantThreadProps,
	type ThreadMessage
} from '$lib/components/AssistantThread.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = AssistantThreadProps;

const RECIPE_ID = '1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f';

function ask(text: string, id = 'u1'): ThreadMessage {
	return { id, role: 'user', parts: [{ type: 'text', text }] };
}

function answer(text: string, id = 'a1'): ThreadMessage {
	return { id, role: 'assistant', parts: [{ type: 'text', text }] };
}

const discovery: ThreadMessage[] = [
	ask('Something warming with lentils?'),
	{
		id: 'a1',
		role: 'assistant',
		parts: [
			{
				type: 'tool-search_recipes',
				toolCallId: 't1',
				state: 'output-available',
				input: { query: 'lentil' },
				output: [{ id: RECIPE_ID, name: 'Lentil and squash soup' }]
			},
			{
				type: 'tool-semantic_search_recipes',
				toolCallId: 't2',
				state: 'output-available',
				input: { query: 'warming winter bowl' },
				output: [{ id: RECIPE_ID, name: 'Lentil and squash soup' }]
			},
			{
				type: 'text',
				text: `Try [Lentil and squash soup](/recipes/${RECIPE_ID}) — it is the most warming thing the library has.`
			}
		]
	}
];

const HOSTILE = [
	'# Heading',
	'<script>window.__pwned = true;<\/script>',
	'<img src="x" onerror="window.__pwned = true">',
	'<a href="javascript:window.__pwned = true">click me</a>',
	'Still [a real link](/recipes/' + RECIPE_ID + ').',
	`And an invented host on [one it made up](https://cookmarks.example/recipes/${RECIPE_ID}).`
].join('\n\n');

const DRAFT = '.draft';
const SEND = '.send';

const unit: VerifiableUnit<Props> = {
	id: 'assistant-thread',
	title: 'Assistant thread',
	description:
		'The chat surface: the transcript of what was asked and answered, the quiet ledger of which tools the assistant reached for, the thinking state, and the composer.',
	kind: 'component',
	component: AssistantThread,
	fixtures: [
		{
			id: 'empty',
			description: 'nothing asked yet — the opening invitation and an idle composer',
			props: { messages: [] }
		},
		{
			id: 'discovery',
			description: 'a discovery ask that fanned out over two searches before answering',
			props: { messages: discovery }
		},
		{
			id: 'streaming',
			description: 'a reply arriving — the thinking indicator shows and the composer is held',
			props: { messages: [ask('What can I do with fennel?')], status: 'streaming' }
		},
		{
			id: 'unavailable',
			description: 'no AI provider configured (the chat endpoint answered 409)',
			props: { messages: [], unavailable: true }
		},
		{
			id: 'failed',
			description: 'the turn errored — the transcript keeps what was said and shows why',
			props: {
				messages: [ask('What can I do with fennel?')],
				status: 'error',
				error: 'The assistant could not finish that answer.'
			}
		},
		{
			id: 'compose',
			description: 'typing a question and pressing Ask fires the send handler',
			props: { messages: [] },
			act: ({ type, click }) => {
				type(DRAFT, 'what should I cook tonight');
				click(SEND);
			}
		},
		{
			id: 'hostile-markdown',
			description: 'probe: an assistant reply carrying script tags, an onerror image and a javascript: link',
			probe: true,
			props: { messages: [ask('be evil'), answer(HOSTILE)] }
		},
		{
			id: 'malformed-tool-part',
			description: 'probe: tool parts with no input, no output and an unknown state',
			probe: true,
			props: {
				messages: [
					{
						id: 'a1',
						role: 'assistant',
						parts: [
							{ type: 'tool-search_recipes', state: 'input-streaming' },
							{ type: 'tool-', state: 'output-available', output: 'not a list' },
							{ type: 'unheard-of-part', payload: { deep: [1, 2, 3] } }
						]
					}
				]
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { messages: discovery }
		}
	],
	invariants: [
		{
			id: 'empty-state',
			description: 'an unasked thread shows the invitation, no messages',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.msg')) return 'no messages expected';
				return root.querySelector('.opening') !== null || 'opening invitation missing';
			}
		},
		{
			id: 'transcript-rendered',
			description: 'every message renders in order, with its role on the contract',
			onlyFixtures: ['discovery'],
			check: ({ contract, root, props }) => {
				const rendered = root.querySelectorAll('.msg');
				if (rendered.length !== props.messages.length)
					return `expected ${props.messages.length} messages, saw ${rendered.length}`;
				return contract.roles === 'user,assistant' || `roles=${contract.roles}`;
			}
		},
		{
			id: 'tool-trace-shown',
			description: 'each tool call leaves a trace line naming the tool and what it asked for',
			onlyFixtures: ['discovery'],
			check: ({ contract, root }) => {
				if (contract['tool-parts'] !== '2') return `tool-parts=${contract['tool-parts']}`;
				const traces = [...root.querySelectorAll('.trace')];
				if (traces.length !== 2) return `saw ${traces.length} trace lines`;
				const text = traces[0].textContent ?? '';
				if (!text.includes('search recipes')) return `first trace does not name its tool: ${text}`;
				return text.includes('lentil') || `first trace does not show its query: ${text}`;
			}
		},
		{
			id: 'recipe-links-are-internal',
			description: 'a recipe the assistant names is a link the app can route',
			onlyFixtures: ['discovery'],
			check: ({ root }) => {
				const link = root.querySelector('.reply a');
				if (!link) return 'the reply carries no link';
				const href = link.getAttribute('href') ?? '';
				return href === `/recipes/${RECIPE_ID}` || `href=${href}`;
			}
		},
		{
			id: 'streaming-holds-the-composer',
			description: 'while a reply streams the thinking indicator shows and Ask is disabled',
			onlyFixtures: ['streaming'],
			check: ({ contract, root }) => {
				if (contract.streaming !== 'true') return `streaming=${contract.streaming}`;
				if (!root.querySelector('.working')) return 'no thinking indicator';
				const send = root.querySelector('.send') as HTMLButtonElement | null;
				return send?.disabled === true || 'Ask is not disabled mid-stream';
			}
		},
		{
			id: 'unavailable-state',
			description: 'with no provider the composer is disabled and the reason is stated',
			onlyFixtures: ['unavailable'],
			check: ({ contract, root }) => {
				if (contract.unavailable !== 'true') return `unavailable=${contract.unavailable}`;
				const draft = root.querySelector('.draft') as HTMLTextAreaElement | null;
				if (draft?.disabled !== true) return 'the composer is still enabled';
				return (root.textContent ?? '').includes('No AI provider') || 'no reason given';
			}
		},
		{
			id: 'error-surfaces',
			description: 'a failed turn shows the error without losing the transcript',
			onlyFixtures: ['failed'],
			check: ({ root }) => {
				if (!root.querySelector('.notice.error')) return 'no error notice';
				return root.querySelectorAll('.msg').length === 1 || 'the transcript was dropped';
			}
		},
		{
			id: 'compose-wires',
			description: 'pressing Ask sends the typed question and clears the field',
			onlyFixtures: ['compose'],
			check: ({ root }) => {
				const draft = root.querySelector('.draft') as HTMLTextAreaElement | null;
				return draft?.value === '' || `the draft was not cleared: ${draft?.value}`;
			}
		},
		{
			id: 'hostile-markdown-is-sanitised',
			description: 'nothing executable survives into the DOM, but real links do',
			onlyFixtures: ['hostile-markdown'],
			check: ({ root }) => {
				if (root.querySelector('script')) return 'a script element survived sanitisation';
				if (root.querySelector('.reply img')) return 'a model-supplied image survived';
				const attributed = [...root.querySelectorAll('*')].find((el) =>
					[...el.attributes].some((a) => a.name.toLowerCase().startsWith('on'))
				);
				if (attributed) return `an inline event handler survived on <${attributed.tagName}>`;
				const hrefs = [...root.querySelectorAll('a')].map((a) => a.getAttribute('href') ?? '');
				if (hrefs.some((h) => h.toLowerCase().startsWith('javascript:')))
					return 'a javascript: link survived';
				if (!root.querySelector('.reply h1')) return 'the Markdown heading did not render';
				if (!hrefs.includes(`/recipes/${RECIPE_ID}`)) return 'the real link was stripped too';
				return (
					hrefs.every((h) => !h.includes('cookmarks.example')) ||
					'an invented hostname survived on an app link'
				);
			}
		},
		{
			id: 'malformed-tool-parts-render',
			description: 'a half-formed or unknown part never breaks the transcript',
			onlyFixtures: ['malformed-tool-part'],
			check: ({ root }) => {
				if (!root.querySelector('.msg')) return 'the message did not render';
				const traces = [...root.querySelectorAll('.trace')];
				if (traces.length !== 2) return `expected 2 trace lines, saw ${traces.length}`;
				return (traces[0].textContent ?? '').includes('running') || 'an in-flight call is not marked';
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
