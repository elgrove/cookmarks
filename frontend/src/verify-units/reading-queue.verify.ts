import ReadingQueue, {
	type QueuedBookRow,
	type ReadingQueueProps
} from '$lib/components/ReadingQueue.svelte';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ReadingQueueProps;

function book(over: Partial<QueuedBookRow> = {}): QueuedBookRow {
	return {
		id: over.id ?? 'b1',
		title: over.title ?? 'A Cookbook',
		author: over.author ?? 'An Author',
		hasCover: over.hasCover ?? false,
		recipeCount: over.recipeCount ?? 40
	};
}

const books: QueuedBookRow[] = [
	book({ id: 'b1', title: 'An Everlasting Meal', author: 'Tamar Adler', hasCover: true, recipeCount: 87 }),
	book({ id: 'b2', title: 'Salt, Fat, Acid, Heat', author: 'Samin Nosrat', recipeCount: 220 }),
	book({ id: 'b3', title: 'Not Yet Extracted', author: 'Someone New', recipeCount: 0 })
];

const unit: VerifiableUnit<Props> = {
	id: 'reading-queue',
	title: 'Reading queue',
	description:
		'The books queued to read next, newest first: a numbered index with cover plates where present, a per-row remove, and a designed empty state.',
	kind: 'component',
	component: ReadingQueue,
	fixtures: [
		{
			id: 'populated',
			description: 'a queue of books, numbered, covers where present',
			props: { books }
		},
		{
			id: 'empty',
			description: 'nothing queued — the calm empty state',
			props: { books: [] }
		},
		{
			id: 'remove',
			description: 'removing a row fires the handler and echoes the id',
			props: { books },
			act: ({ click }) => click('.row .remove')
		},
		{
			id: 'overlong',
			description: 'probe: many books with overlong unicode titles all render',
			probe: true,
			props: {
				books: Array.from({ length: 24 }, (_, i) =>
					book({
						id: `x${i}`,
						title: `Très Long Cookbook Title — ${i} — 你好 ${'noodles '.repeat(4)}`,
						author: `Author With A Remarkably Long Name ${i}`,
						hasCover: i % 2 === 0,
						recipeCount: i * 97
					})
				)
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { books }
		}
	],
	invariants: [
		{
			id: 'rows-match-count',
			description: 'every queued book renders as a row and the contract count agrees',
			onlyFixtures: ['populated', 'overlong'],
			check: ({ contract, root, props }) => {
				const rows = root.querySelectorAll('.row');
				if (rows.length !== props.books.length)
					return `expected ${props.books.length} rows, saw ${rows.length}`;
				return contract.count === String(props.books.length) || `count=${contract.count}`;
			}
		},
		{
			id: 'rows-link-to-books',
			description: 'each row links its title to the book detail page',
			onlyFixtures: ['populated'],
			check: ({ root }) => {
				const links = [...root.querySelectorAll('.row .title')];
				if (links.length === 0) return 'no title links';
				for (const link of links) {
					const href = link.getAttribute('href') ?? '';
					if (!/^\/books\/.+/.test(href)) return `title href not a book page: ${href}`;
				}
				return true;
			}
		},
		{
			id: 'empty-state',
			description: 'an empty queue shows the empty message, no rows',
			onlyFixtures: ['empty'],
			check: ({ contract, root }) => {
				if (contract.empty !== 'true') return `empty=${contract.empty}`;
				if (root.querySelector('.row')) return 'no rows expected';
				return (root.textContent ?? '').includes('Nothing queued yet') || 'empty message missing';
			}
		},
		{
			id: 'remove-wires',
			description: 'removing the first row echoes its id into the contract',
			onlyFixtures: ['remove'],
			check: ({ contract }) => contract.removed === 'b1' || `removed=${contract.removed}`
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
