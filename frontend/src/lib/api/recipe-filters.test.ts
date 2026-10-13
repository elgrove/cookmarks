import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import { recipeFiltersSchema, type RecipeFilters } from './recipe-filters';
import { criteriaFromParams, criteriaToParams, hasCriteria, searchContextQuery } from './recipes';

const filters: RecipeFilters = {
	version: 1,
	match: 'any',
	rules: [
		{ field: 'description', operator: 'contains', value: 'Crème 10%_ & 你好' },
		{ field: 'favourite', operator: 'eq', value: false }
	]
};
describe('advanced filter URL contract', () => {
	it('pins the shared request example', () => {
		const example = JSON.parse(
			fs.readFileSync(`${process.cwd()}/../contract/recipefilters.example.json`, 'utf8')
		);
		expect(recipeFiltersSchema.parse(example)).toEqual(example);
	});
	it('round trips all rules alongside legacy criteria', () => {
		const criteria = {
			filters,
			q: 'dinner',
			keywords: ['quick'],
			bookId: 'book',
			author: 'Author',
			sort: 'name' as const,
			seed: 42,
			offset: 30
		};
		expect(criteriaFromParams(criteriaToParams(criteria))).toEqual(criteria);
		expect(hasCriteria({ filters })).toBe(true);
		const context = new URLSearchParams(searchContextQuery(criteria));
		expect(context.get('context')).toBe('search');
		expect(context.has('offset')).toBe(false);
		expect(criteriaFromParams(context).filters).toEqual(filters);
	});
	it('keeps legacy keyword URLs and normalises stored identity', () => {
		expect(
			criteriaFromParams(new URLSearchParams('keyword=Quick&keyword=slow++roast')).keywords
		).toEqual(['quick', 'slow roast']);
	});
	it.each([
		'{',
		'null',
		'{"version":2,"match":"all","rules":[]}',
		'{"version":1,"match":"all","rules":[{"field":"name","operator":"contains","value":""}]}'
	])('rejects invalid filters: %s', (raw) => {
		expect(() => criteriaFromParams(new URLSearchParams({ filters: raw }))).toThrow();
	});
	it('treats empty any/all as no advanced restriction', () => {
		expect(hasCriteria({ filters: { version: 1, match: 'any', rules: [] } })).toBe(false);
		expect(
			criteriaToParams({ filters: { version: 1, match: 'all', rules: [] } }).has('filters')
		).toBe(false);
	});
	it('rejects excessive or incompatible rules', () => {
		expect(
			recipeFiltersSchema.safeParse({ ...filters, rules: Array(21).fill(filters.rules[0]) }).success
		).toBe(false);
		expect(
			recipeFiltersSchema.safeParse({
				...filters,
				rules: [{ field: 'has_image', operator: 'eq', value: 'true' }]
			}).success
		).toBe(false);
	});
});
