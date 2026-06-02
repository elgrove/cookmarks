import ReaderChrome, { type TocEntry } from '$lib/components/ReaderChrome.svelte';
import type { VerifiableUnit } from '$lib/verify/types';
import { z } from 'zod';

type Props = {
	title: string;
	author: string;
	backHref: string;
	toc: TocEntry[];
	currentHref: string | null;
	progress: number;
	fontScale: number;
	theme: 'light' | 'dark';
	onSelectToc: (href: string) => void;
	onPrev: () => void;
	onNext: () => void;
	onFontDec: () => void;
	onFontInc: () => void;
	onToggleTheme: () => void;
};

const tocEntrySchema = z.object({
	label: z.string(),
	href: z.string(),
	depth: z.number().int().nonnegative()
});

// Callbacks are stripped by safeParse (unknown keys) — only the data props are validated.
const propsSchema = z.object({
	title: z.string(),
	author: z.string(),
	backHref: z.string(),
	toc: z.array(tocEntrySchema),
	currentHref: z.string().nullable(),
	progress: z.number(),
	fontScale: z.number(),
	theme: z.enum(['light', 'dark'])
});

const noop = () => {};

const TOC: TocEntry[] = [
	{ label: 'Introduction', href: 'intro.xhtml', depth: 0 },
	{ label: 'Spring', href: 'ch1.xhtml', depth: 0 },
	{ label: 'Asparagus & Peas', href: 'ch1.xhtml#s1', depth: 1 },
	{ label: 'Wild Garlic Soup', href: 'ch1.xhtml#s2', depth: 1 },
	{ label: 'Summer', href: 'ch2.xhtml', depth: 0 },
	{ label: 'Autumn', href: 'ch3.xhtml', depth: 0 },
	{ label: 'Winter', href: 'ch4.xhtml', depth: 0 }
];

const base: Props = {
	title: 'The Zen Kitchen',
	author: 'Adam Liaw',
	backHref: '/books/a0054f3d-3f99-4502-aa48-dc933c13fab8',
	toc: TOC,
	currentHref: null,
	progress: 0.42,
	fontScale: 1,
	theme: 'light',
	onSelectToc: noop,
	onPrev: noop,
	onNext: noop,
	onFontDec: noop,
	onFontInc: noop,
	onToggleTheme: noop
};

const openToc = ({ click }: { click: (selector: string) => void }) =>
	click('button[aria-expanded]');

const unit: VerifiableUnit<Props> = {
	id: 'reader-chrome',
	title: 'Reader chrome',
	description:
		'The immersive EPUB reader frame: a top bar (back · title · contents · text size · theme), a progress line, page navigation, and a slide-in table-of-contents drawer.',
	kind: 'component',
	component: ReaderChrome,
	propsSchema,
	fixtures: [
		{
			id: 'reading',
			description: 'mid-book, a chapter highlighted, drawer closed',
			props: { ...base, currentHref: 'ch1.xhtml#s1', progress: 0.42 }
		},
		{
			id: 'start',
			description: 'the very start of the book: 0% progress',
			props: { ...base, progress: 0 }
		},
		{
			id: 'finished',
			description: 'the end of the book: 100% progress',
			props: { ...base, currentHref: 'ch4.xhtml', progress: 1 }
		},
		{
			id: 'dark',
			description: 'dark theme: the toggle shows the moon glyph',
			props: { ...base, theme: 'dark' }
		},
		{
			id: 'contents-open',
			description: 'opening the drawer reveals every TOC entry',
			props: { ...base, currentHref: 'ch2.xhtml' },
			act: openToc
		},
		{
			id: 'no-toc',
			description: 'a book with no navigation shows a calm empty message, not a broken drawer',
			props: { ...base, toc: [] },
			act: openToc
		},
		{
			id: 'deep-toc',
			description: 'probe: a large, deeply-nested TOC with overlong labels must not break the drawer',
			probe: true,
			props: {
				...base,
				toc: Array.from({ length: 60 }, (_, i) => ({
					label:
						i % 3 === 0
							? `A chapter with an unreasonably long title that should truncate or wrap gracefully #${i}`
							: `Entry ${i}`,
					href: `ch${i}.xhtml`,
					depth: i % 4
				}))
			},
			act: openToc
		},
		{
			id: 'contract-lie',
			description: 'expectFail: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: base
		}
	],
	invariants: [
		{
			id: 'toc-count',
			description: 'the toc-count contract matches the supplied TOC length',
			check: ({ contract, props }) =>
				Number(contract['toc-count']) === props.toc.length ||
				`toc-count=${contract['toc-count']} expected ${props.toc.length}`
		},
		{
			id: 'progress-contract',
			description: 'the progress contract is the supplied fraction as a clamped percent',
			check: ({ contract, props }) => {
				const want = Math.max(0, Math.min(100, Math.round(props.progress * 100)));
				return Number(contract.progress) === want || `progress=${contract.progress} expected ${want}`;
			}
		},
		{
			id: 'closed-initially',
			description: 'with no interaction the drawer is absent and flagged closed',
			check: ({ root, contract, fixture }) => {
				if (fixture.act) return true; // fixtures that open the drawer are checked elsewhere
				if (contract['toc-open'] !== 'false') return `toc-open=${contract['toc-open']}`;
				return root.querySelector('.drawer') === null || 'drawer rendered before opening';
			}
		},
		{
			id: 'opens-on-click',
			description: 'clicking Contents opens the drawer and lists every entry',
			onlyFixtures: ['contents-open', 'deep-toc'],
			check: ({ root, contract, props }) => {
				if (contract['toc-open'] !== 'true') return `toc-open=${contract['toc-open']}`;
				if (root.querySelector('.drawer') === null) return 'drawer not rendered after click';
				const items = root.querySelectorAll('.toc-item').length;
				return items === props.toc.length || `rendered ${items} items, expected ${props.toc.length}`;
			}
		},
		{
			id: 'empty-toc-message',
			description: 'a book with no TOC shows the empty message and no entries',
			onlyFixtures: ['no-toc'],
			check: ({ root }) => {
				if (root.querySelector('.toc-item')) return 'rendered a TOC item for an empty TOC';
				return root.querySelector('.toc-empty') !== null || 'empty-TOC message missing';
			}
		},
		{
			id: 'back-link',
			description: 'the back affordance links to the book detail page',
			check: ({ root, props }) => {
				const href = root.querySelector('a.back')?.getAttribute('href');
				return href === props.backHref || `back href=${href} expected ${props.backHref}`;
			}
		},
		{
			id: 'page-controls',
			description: 'both page-navigation buttons are present',
			check: ({ root }) => {
				const n = root.querySelectorAll('.bar.bottom .page').length;
				return n === 2 || `found ${n} page buttons, expected 2`;
			}
		},
		{
			id: 'current-chapter',
			description: 'the current chapter label is surfaced in the location readout',
			onlyFixtures: ['reading'],
			check: ({ root, props }) => {
				const want = props.toc.find((t) => t.href === props.currentHref)?.label ?? '';
				const got = root.querySelector('.loc .chap')?.textContent?.trim() ?? '';
				return got === want || `chapter label="${got}" expected "${want}"`;
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
