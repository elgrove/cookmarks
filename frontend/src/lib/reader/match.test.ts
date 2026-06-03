import { describe, expect, it } from 'vitest';
import { buildRecipeIndex, matchHeading, normaliseTitle } from './match';

const entry = (id: string, name: string, is_favourite = false) => ({ id, name, is_favourite });

describe('normaliseTitle', () => {
	it('lowercases and collapses punctuation + whitespace', () => {
		expect(normaliseTitle('  Chicken   Soup!! ')).toBe('chicken soup');
	});
	it('drops apostrophes so possessives match', () => {
		expect(normaliseTitle("Rosetta's Trofie")).toBe('rosettas trofie');
	});
	it('strips accents', () => {
		expect(normaliseTitle('Crème Brûlée')).toBe('creme brulee');
	});
	it('strips a leading numbering prefix', () => {
		expect(normaliseTitle('12. Chana Masala')).toBe('chana masala');
	});
	it('strips a leading chapter label', () => {
		expect(normaliseTitle('Chapter Three: Soups')).toBe('soups');
	});
	it('expands ampersand', () => {
		expect(normaliseTitle('Rice & Peas')).toBe('rice and peas');
	});
	it('is empty for punctuation-only input', () => {
		expect(normaliseTitle('—  •  —')).toBe('');
	});
});

describe('buildRecipeIndex', () => {
	it('keys by normalised name; first writer wins on collision', () => {
		const idx = buildRecipeIndex([entry('a', 'Dal'), entry('b', 'dal'), entry('c', 'Chana Masala', true)]);
		expect(idx.get('dal')?.id).toBe('a');
		expect(idx.get('chana masala')?.isFavourite).toBe(true);
	});
});

describe('matchHeading', () => {
	const idx = buildRecipeIndex([
		entry('r1', "Rosetta's Trofie with Basil Sauce"),
		entry('r2', 'Chana Masala', true),
		entry('r3', 'Dal')
	]);

	it('matches case-insensitively on exact normalised title', () => {
		expect(matchHeading("ROSETTA'S TROFIE WITH BASIL SAUCE", idx)?.id).toBe('r1');
	});
	it('matches a heading carrying a trailing qualifier (prefix fallback)', () => {
		expect(matchHeading('Chana Masala (Serves 4)', idx)?.id).toBe('r2');
	});
	it('carries the favourite state through', () => {
		expect(matchHeading('Chana Masala', idx)?.isFavourite).toBe(true);
	});
	it('still exact-matches a short title', () => {
		expect(matchHeading('Dal', idx)?.id).toBe('r3');
	});
	it('does not fuzzy-match a short title against a longer word', () => {
		expect(matchHeading('Dalek', idx)).toBeNull();
	});
	it('returns null for an unrelated heading', () => {
		expect(matchHeading('Introduction', idx)).toBeNull();
	});
	it('returns null for an empty heading', () => {
		expect(matchHeading('   ', idx)).toBeNull();
	});
});
