import { describe, expect, it } from 'vitest';
import { cleanTitle, pageTitle, titleSubtitle } from './title';

describe('pageTitle', () => {
	it('puts the page before the brand', () => {
		expect(pageTitle('Recipes')).toBe('Recipes · Cookmarks');
	});

	it('is bare on the home page', () => {
		expect(pageTitle()).toBe('Cookmarks');
		expect(pageTitle('  ')).toBe('Cookmarks');
	});
});

describe('cleanTitle', () => {
	it('drops the Calibre subtitle', () => {
		expect(cleanTitle('Persiana: Recipes from…')).toBe('Persiana');
		expect(cleanTitle('Persiana')).toBe('Persiana');
	});

});

describe('titleSubtitle', () => {
	it('keeps the subtitle, softening further colons', () => {
		expect(titleSubtitle('A: B: C')).toBe('B — C');
		expect(titleSubtitle('Persiana')).toBe('');
	});
});
