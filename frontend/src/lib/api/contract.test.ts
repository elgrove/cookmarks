import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
	bookFiltersResponseSchema,
	bookFilterSchema,
	booksResponseSchema,
	bookSummarySchema
} from './books';
import { homeSchema } from './home';
import { keywordSummarySchema, recipeDetailSchema, recipeSearchResultsSchema } from './recipes';
import { listDetailSchema, listMembershipSchema, listSummarySchema } from './lists';

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
});
