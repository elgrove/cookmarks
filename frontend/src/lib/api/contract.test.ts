import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
	bookFiltersResponseSchema,
	bookFilterSchema,
	booksResponseSchema,
	bookSummarySchema,
	recipeIndexEntrySchema,
	recipeIndexResponseSchema
} from './books';
import { homeSchema } from './home';
import {
	keywordSummarySchema,
	recipeDetailSchema,
	recipeSearchResultsSchema,
	semanticSearchResultsSchema,
	similarRecipesSchema
} from './recipes';
import { listDetailSchema, listMembershipSchema, listSummarySchema } from './lists';
import { extractionRunSchema, reviewQuestionSchema } from './extraction';
import { configSchema } from './config';

// Frontend half of the API wire contract (see /contract/README.md): the Zod
// schemas must accept the shared example the backend pins itself to, and reject
// a drifted copy — so a one-sided rename fails CI, not just at runtime.
// cwd is the frontend root under both `npm run verify` and CI; the contract dir
// sits one level up at the repo root.
const load = (name: string) =>
	JSON.parse(readFileSync(resolve(process.cwd(), '..', 'contract', name), 'utf8'));

describe('api wire contract', () => {
	it('accepts the books example and the list wrapper', () => {
		const example = load('books.example.json');
		expect(() => bookSummarySchema.parse(example)).not.toThrow();
		expect(() => booksResponseSchema.parse([example])).not.toThrow();
	});

	it('rejects a books example with a drifted field name', () => {
		const example = load('books.example.json');
		const { recipe_count, ...rest } = example;
		const drifted = { ...rest, recipeCount: recipe_count };
		expect(() => bookSummarySchema.parse(drifted)).toThrow();
	});

	it('accepts the book filters example and the list wrapper', () => {
		const example = load('bookfilters.example.json');
		expect(() => bookFilterSchema.parse(example)).not.toThrow();
		expect(() => bookFiltersResponseSchema.parse([example])).not.toThrow();
	});

	it('accepts the recipe-index example and the list wrapper', () => {
		const example = load('recipeindex.example.json');
		expect(() => recipeIndexEntrySchema.parse(example)).not.toThrow();
		expect(() => recipeIndexResponseSchema.parse([example])).not.toThrow();
	});

	it('rejects a recipe-index example with a drifted field name', () => {
		const example = load('recipeindex.example.json');
		const { is_favourite, ...rest } = example;
		const drifted = { ...rest, isFavourite: is_favourite };
		expect(() => recipeIndexEntrySchema.parse(drifted)).toThrow();
	});

	it('rejects a book filters example with a drifted field name', () => {
		const example = load('bookfilters.example.json');
		const { title, ...rest } = example;
		const drifted = { ...rest, bookTitle: title };
		expect(() => bookFilterSchema.parse(drifted)).toThrow();
	});

	it('accepts the home example', () => {
		expect(() => homeSchema.parse(load('home.example.json'))).not.toThrow();
	});

	it('accepts the recipe example', () => {
		expect(() => recipeDetailSchema.parse(load('recipe.example.json'))).not.toThrow();
	});

	it('rejects a recipe example with a drifted field name', () => {
		const example = load('recipe.example.json');
		const { has_image, ...rest } = example;
		const drifted = { ...rest, hasImage: has_image };
		expect(() => recipeDetailSchema.parse(drifted)).toThrow();
	});

	it('accepts the recipes search example', () => {
		expect(() => recipeSearchResultsSchema.parse(load('recipes.example.json'))).not.toThrow();
	});

	it('rejects a recipes example with a drifted field name', () => {
		const example = load('recipes.example.json');
		const { book_title, ...rest } = example.items[0];
		const drifted = { ...example, items: [{ ...rest, bookTitle: book_title }] };
		expect(() => recipeSearchResultsSchema.parse(drifted)).toThrow();
	});

	it('accepts the keywords example', () => {
		expect(() => keywordSummarySchema.parse(load('keywords.example.json'))).not.toThrow();
	});

	it('accepts the similar-recipes example', () => {
		expect(() => similarRecipesSchema.parse(load('similar.example.json'))).not.toThrow();
	});

	it('rejects a similar-recipes example with a drifted field name', () => {
		const example = load('similar.example.json');
		const { book_author, ...rest } = example.items[0];
		const drifted = { ...example, items: [{ ...rest, bookAuthor: book_author }] };
		expect(() => similarRecipesSchema.parse(drifted)).toThrow();
	});

	it('accepts the semantic search example', () => {
		expect(() =>
			semanticSearchResultsSchema.parse(load('semanticsearch.example.json'))
		).not.toThrow();
	});

	it('rejects a semantic search example with a drifted field name', () => {
		const example = load('semanticsearch.example.json');
		const { distance, ...rest } = example.items[0];
		const drifted = { ...example, items: [{ ...rest, score: distance }] };
		expect(() => semanticSearchResultsSchema.parse(drifted)).toThrow();
	});

	it('accepts the list summary example and the list wrapper', () => {
		const example = load('listsummary.example.json');
		expect(() => listSummarySchema.parse(example)).not.toThrow();
	});

	it('rejects a list summary example with a drifted field name', () => {
		const example = load('listsummary.example.json');
		const { recipe_count, ...rest } = example;
		const drifted = { ...rest, recipeCount: recipe_count };
		expect(() => listSummarySchema.parse(drifted)).toThrow();
	});

	it('accepts the list detail example', () => {
		expect(() => listDetailSchema.parse(load('listdetail.example.json'))).not.toThrow();
	});

	it('accepts the list membership example', () => {
		expect(() => listMembershipSchema.parse(load('listmembership.example.json'))).not.toThrow();
	});

	it('rejects a list membership example with a drifted field name', () => {
		const example = load('listmembership.example.json');
		const { contains, ...rest } = example;
		const drifted = { ...rest, inList: contains };
		expect(() => listMembershipSchema.parse(drifted)).toThrow();
	});

	it('accepts the extraction-run example', () => {
		expect(() => extractionRunSchema.parse(load('extractionrun.example.json'))).not.toThrow();
	});

	it('rejects an extraction-run example with a drifted field name', () => {
		const example = load('extractionrun.example.json');
		const { chapters_processed, ...rest } = example;
		const drifted = { ...rest, chaptersProcessed: chapters_processed };
		expect(() => extractionRunSchema.parse(drifted)).toThrow();
	});

	it('accepts the review-question example', () => {
		expect(() => reviewQuestionSchema.parse(load('reviewquestion.example.json'))).not.toThrow();
	});

	it('rejects a review-question example with a drifted field name', () => {
		const example = load('reviewquestion.example.json');
		const { label, ...rest } = example.choices[0];
		const drifted = { ...example, choices: [{ ...rest, text: label }] };
		expect(() => reviewQuestionSchema.parse(drifted)).toThrow();
	});

	it('accepts an extraction run paused at review with a pending question', () => {
		const example = {
			...load('extractionrun.example.json'),
			status: 'review',
			pending_question: load('reviewquestion.example.json')
		};
		expect(() => extractionRunSchema.parse(example)).not.toThrow();
	});

	it('accepts the config example', () => {
		expect(() => configSchema.parse(load('config.example.json'))).not.toThrow();
	});

	it('rejects a config example with a drifted field name', () => {
		const example = load('config.example.json');
		const { api_key_set, ...rest } = example;
		const drifted = { ...rest, apiKeySet: api_key_set };
		expect(() => configSchema.parse(drifted)).toThrow();
	});
});
