import BookMetadataEditor, {
	type BookMetadataDraft,
	type BookMetadataEditorProps
} from '$lib/components/BookMetadataEditor.svelte';
import type { BookMetadataUpdate } from '$lib/api/books';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = BookMetadataEditorProps;

const OPEN = '.edit-open';
const SAVE = '.edit-save';
const CANCEL = '.edit-cancel';
const TITLE = '.edit-title';
const AUTHOR = '.edit-author';
const ISBN = '.edit-isbn';
const KW_INPUT = '.kw-input';

const draftSchema = z.object({
	title: z.string(),
	author: z.string(),
	isbn: z.string().nullable(),
	pubdate: z.string().nullable(),
	description: z.string(),
	keywords: z.array(z.string())
});

const populated: BookMetadataDraft = {
	title: 'Salt, Fat, Acid, Heat',
	author: 'Samin Nosrat',
	isbn: '9781476753836',
	pubdate: '2017-04-25',
	description: 'Mastering the elements of good cooking.',
	keywords: ['Italian', 'Pasta']
};

const emptyOptionals: BookMetadataDraft = {
	title: '1,000 Indian Recipes',
	author: 'Neelam Batra',
	isbn: null,
	pubdate: null,
	description: '',
	keywords: []
};

const savedTitle = 'Salt, Fat, Acid, Heat (Revised)';

const unit: VerifiableUnit<Props> = {
	id: 'book-metadata-editor',
	title: 'Book metadata editor',
	description:
		'The admin metadata editor on a book: closed it is a single "Edit details" action; open it offers labelled controls for title, author, ISBN, publication date, description and keyword tokens, with Save/Cancel. Required-field and server errors never close the form; success closes it.',
	kind: 'component',
	component: BookMetadataEditor,
	propsSchema: z.object({ initial: draftSchema }),
	fixtures: [
		{
			id: 'closed',
			description: 'at rest — a single Edit action, no form',
			props: { initial: populated }
		},
		{
			id: 'open',
			description: 'the open form carries the book’s current metadata',
			props: { initial: populated },
			act: ({ click }) => click(OPEN)
		},
		{
			id: 'empty-optionals',
			description: 'a book with nothing optional set opens cleanly with empty optionals',
			props: { initial: emptyOptionals },
			act: ({ click }) => click(OPEN)
		},
		{
			id: 'validation-error',
			description: 'clearing the title invalidates the form without closing it',
			props: { initial: populated },
			act: ({ click, type }) => {
				click(OPEN);
				type(TITLE, '   ');
			}
		},
		{
			id: 'save',
			description: 'saving calls back with the update and closes the form',
			props: {
				initial: populated,
				onSave: async (update: BookMetadataUpdate) => {
					if (update.title !== savedTitle) throw new Error(`title=${update.title}`);
					return { title: savedTitle, keywords: ['Italian', 'Pasta', 'Revised'] };
				}
			},
			act: async ({ click, type, wait }) => {
				click(OPEN);
				type(TITLE, savedTitle);
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'cancel',
			description: 'cancel discards edits and closes without calling back',
			props: {
				initial: populated,
				onSave: () => {
					throw new Error('onSave must not be called on cancel');
				}
			},
			act: ({ click, type }) => {
				click(OPEN);
				type(TITLE, 'Discarded title');
				click(CANCEL);
			}
		},
		{
			id: 'server-error',
			description: 'a rejected save surfaces the server error and keeps the form open',
			props: {
				initial: populated,
				onSave: () => Promise.reject(new Error('Title is already in use'))
			},
			act: async ({ click, wait }) => {
				click(OPEN);
				click(SAVE);
				await wait(0);
			}
		},
		{
			id: 'keyword-tokens',
			description: 'probe: comma-separated keyword input splits into removable tokens',
			probe: true,
			props: { initial: emptyOptionals },
			act: ({ click, type }) => {
				click(OPEN);
				type(KW_INPUT, 'Pasta,  Quick ,, pasta');
			}
		},
		{
			id: 'contract-lie',
			description: 'expectFail: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { initial: populated }
		}
	],
	invariants: [
		{
			id: 'closed-rests',
			description: 'closed: one Edit action, no form controls',
			onlyFixtures: ['closed'],
			check: ({ contract, root }) => {
				if (contract.state !== 'closed') return `state=${contract.state}`;
				if (!root.querySelector(OPEN)) return 'no Edit action';
				return root.querySelector('form') === null || 'form rendered while closed';
			}
		},
		{
			id: 'open-carries-values',
			description: 'open: the form carries the current metadata and two keywords',
			onlyFixtures: ['open'],
			check: ({ contract, root, props }) => {
				if (contract.state !== 'open') return `state=${contract.state}`;
				const title = root.querySelector<HTMLInputElement>(TITLE)?.value ?? '';
				if (title !== props.initial.title) return `title=${title}`;
				if (contract.keywords !== '2') return `keywords=${contract.keywords}`;
				for (const name of ['Title', 'Author', 'ISBN', 'Publication date', 'Description']) {
					const labels = [...root.querySelectorAll('label')].map((l) => l.textContent?.trim());
					if (!labels.includes(name)) return `missing label ${name}`;
				}
				return true;
			}
		},
		{
			id: 'empty-optionals-open',
			description: 'empty optionals open valid with no keywords',
			onlyFixtures: ['empty-optionals'],
			check: ({ contract, root }) => {
				if (contract.state !== 'open') return `state=${contract.state}`;
				if (contract.valid !== 'true') return `valid=${contract.valid}`;
				if (contract.keywords !== '0') return `keywords=${contract.keywords}`;
				const isbn = root.querySelector<HTMLInputElement>(ISBN)?.value ?? 'missing';
				return isbn === '' || `isbn=${isbn}`;
			}
		},
		{
			id: 'invalid-blocks-save',
			description: 'a blank required field invalidates and disables Save without closing',
			onlyFixtures: ['validation-error'],
			check: ({ contract, root }) => {
				if (contract.state !== 'open') return `state=${contract.state}`;
				if (contract.valid !== 'false') return `valid=${contract.valid}`;
				const save = root.querySelector<HTMLButtonElement>(SAVE);
				if (!save) return 'no Save button';
				if (!save.disabled) return 'Save enabled with a blank title';
				return (root.textContent ?? '').includes('required') || 'required error missing';
			}
		},
		{
			id: 'save-closes',
			description: 'a successful save closes the form with no error',
			onlyFixtures: ['save'],
			check: ({ contract, root }) => {
				if (contract.state !== 'closed') return `state=${contract.state}`;
				if (contract.error !== 'false') return `error=${contract.error}`;
				return root.querySelector(OPEN) !== null || 'Edit action missing after save';
			}
		},
		{
			id: 'cancel-closes-cleanly',
			description: 'cancel closes without an error and without saving',
			onlyFixtures: ['cancel'],
			check: ({ contract, root }) => {
				if (contract.state !== 'closed') return `state=${contract.state}`;
				if (contract.error !== 'false') return `error=${contract.error}`;
				return root.querySelector(OPEN) !== null || 'Edit action missing after cancel';
			}
		},
		{
			id: 'server-error-stays-open',
			description: 'a server rejection keeps the form open with the error surfaced',
			onlyFixtures: ['server-error'],
			check: ({ contract, root }) => {
				if (contract.state !== 'open') return `state=${contract.state}`;
				if (contract.error !== 'true') return `error=${contract.error}`;
				if (contract.saving !== 'false') return `saving=${contract.saving}`;
				return (
					(root.querySelector('.server-error')?.textContent ?? '').includes(
						'Title is already in use'
					) || 'server message missing'
				);
			}
		},
		{
			id: 'keyword-input-splits',
			description: 'comma input becomes tokens (deduped case-insensitively in the control)',
			onlyFixtures: ['keyword-tokens'],
			check: ({ contract, root }) => {
				if (contract.state !== 'open') return `state=${contract.state}`;
				const tokens = [...root.querySelectorAll('.kw-remove')].map((b) =>
					b.getAttribute('data-keyword')
				);
				if (!tokens.includes('Pasta') || !tokens.includes('Quick'))
					return `tokens=${tokens.join(',')}`;
				return true;
			}
		},
		{
			id: 'author-required',
			description: 'the author control is labelled and required',
			onlyFixtures: ['open'],
			check: ({ root }) => {
				const input = root.querySelector<HTMLInputElement>(AUTHOR);
				if (!input) return 'no author input';
				if (!input.required) return 'author not required';
				return (
					root.querySelector('label[for="bme-author"]') !== null || 'author label missing'
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
