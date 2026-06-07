import ReviewPrompt, { type ReviewPromptProps } from '$lib/components/ReviewPrompt.svelte';
import type { ReviewQuestion } from '$lib/api/extraction';
import type { VerifiableUnit } from '$lib/verify/types';

type Props = ReviewPromptProps;

const QUESTION: ReviewQuestion = {
	question: 'Zero images found. Does this cookbook have photos?',
	choices: [
		{ value: 'has_images', label: 'Yes, it has photos' },
		{ value: 'no_images', label: 'No photos' }
	]
};

const questionText = (root: HTMLElement): string =>
	root.querySelector('.question')?.textContent?.trim() ?? '';
const choiceLabel = (root: HTMLElement, value: string): string =>
	root.querySelector(`[data-choice="${value}"]`)?.textContent?.trim() ?? '';

const unit: VerifiableUnit<Props> = {
	id: 'review-prompt',
	title: 'Review prompt',
	description:
		'The human-in-the-loop control for a run paused at REVIEW: surfaces the graph\'s pending question with one button per choice, and on answer drives idle → submitting → submitted (fire-and-forget), or → error if the resume dispatch rejects. Renders an inert "none" state when nothing awaits an answer.',
	kind: 'component',
	component: ReviewPrompt,
	fixtures: [
		{
			id: 'pending',
			description: 'a run paused at review shows its question and both answer choices',
			props: { review: QUESTION }
		},
		{
			id: 'answer',
			description: 'answering a choice dispatches and settles to the submitted confirmation',
			props: { review: QUESTION, onAnswer: () => Promise.resolve() },
			act: async ({ click, wait }) => {
				click('[data-choice="has_images"]');
				await wait(0);
			}
		},
		{
			id: 'no-question',
			description: 'no pending question → an inert control with no choices',
			props: { review: null }
		},
		{
			id: 'reject',
			description: 'probe: a failed resume surfaces an error state, not a false "submitted"',
			probe: true,
			props: { review: QUESTION, onAnswer: () => Promise.reject(new Error('worker down')) },
			act: async ({ click, wait }) => {
				click('[data-choice="no_images"]');
				await wait(0);
			}
		},
		{
			id: 'odd-choice',
			description: 'probe: an oddly-shaped single-choice question still renders one labelled button',
			probe: true,
			props: {
				review: { question: 'Edge?', choices: [{ value: 'x', label: 'Only option' }] }
			}
		},
		{
			id: 'contract-lie',
			description: 'sentinel: a deliberately-failing invariant proves the harness reports truthfully',
			expectFail: true,
			props: { review: QUESTION }
		}
	],
	invariants: [
		{
			id: 'pending-shows-question',
			description: 'a pending review is idle, marked pending, with one choice per answer and the question shown',
			onlyFixtures: ['pending'],
			check: ({ contract, root }) => {
				if (contract.state !== 'idle') return `state=${contract.state}`;
				if (contract.pending !== 'true') return `pending=${contract.pending}`;
				if (contract['choice-count'] !== '2') return `choice-count=${contract['choice-count']}`;
				return questionText(root) === QUESTION.question || `question=${questionText(root)}`;
			}
		},
		{
			id: 'answer-submits',
			description: 'a successful answer lands on the submitted state',
			onlyFixtures: ['answer'],
			check: ({ contract }) => contract.state === 'submitted' || `state=${contract.state}`
		},
		{
			id: 'none-inert',
			description: 'no question → none state, no choices, not pending',
			onlyFixtures: ['no-question'],
			check: ({ contract }) => {
				if (contract.state !== 'none') return `state=${contract.state}`;
				if (contract.pending !== 'false') return `pending=${contract.pending}`;
				return contract['choice-count'] === '0' || `choice-count=${contract['choice-count']}`;
			}
		},
		{
			id: 'reject-errors',
			description: 'a rejected resume lands on the error state (never a false submitted)',
			onlyFixtures: ['reject'],
			check: ({ contract }) => contract.state === 'error' || `state=${contract.state}`
		},
		{
			id: 'odd-labelled',
			description: 'every rendered choice carries a non-empty label',
			onlyFixtures: ['odd-choice'],
			check: ({ contract, root }) => {
				if (contract['choice-count'] !== '1') return `choice-count=${contract['choice-count']}`;
				return choiceLabel(root, 'x').length > 0 || 'choice button has no label';
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
