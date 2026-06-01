import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { booksResponseSchema, bookSummarySchema } from './books';
import { homeSchema } from './home';
import { keywordSummarySchema, recipeDetailSchema, recipeSearchResultsSchema } from './recipes';

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
});
