import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount, tick } from 'svelte';
import AdvancedRecipeSearch from './AdvancedRecipeSearch.svelte';
import RecipesSearch from './RecipesSearch.svelte';
import { emptyFilters, type RecipeFilters } from '$lib/api/recipe-filters';

let instance: ReturnType<typeof mount> | undefined;
let target: HTMLDivElement;
afterEach(async () => {
	if (instance) await unmount(instance);
	target?.remove();
	instance = undefined;
});
function input(selector: string, value: string, event = 'input') {
	const control = target.querySelector<HTMLInputElement>(selector)!;
	control.value = value;
	control.dispatchEvent(new Event(event, { bubbles: true }));
	flushSync();
}
function click(selector: string) {
	target.querySelector<HTMLElement>(selector)!.click();
	flushSync();
}
const filters: RecipeFilters = {
	version: 1,
	match: 'all',
	rules: [{ field: 'method', operator: 'contains', value: 'roast' }]
};
function setup() {
	target = document.createElement('div');
	document.body.appendChild(target);
}
describe('advanced search draft', () => {
	it.each(['author', 'keyword', 'key_ingredient'] as const)(
		'accepts free text without autocomplete for %s',
		(field) => {
			setup();
			const onApply = vi.fn();
			instance = mount(AdvancedRecipeSearch, {
				target,
				props: {
					open: true,
					filters: {
						version: 1,
						match: 'all',
						rules: [{ field, operator: 'contains', value: 'old' }]
					},
					onApply
				}
			});
			flushSync();
			const value = target.querySelector<HTMLInputElement>('input')!;
			expect(value.getAttribute('list')).toBeNull();
			expect(value.autocomplete).toBe('off');
			expect(target.querySelector('datalist')).toBeNull();
			input('input', 'unlisted term');
			target
				.querySelector('form')!
				.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
			flushSync();
			expect(onApply).toHaveBeenCalledWith({
				version: 1,
				match: 'all',
				rules: [{ field, operator: 'contains', value: 'unlisted term' }]
			});
		}
	);

	it('does not apply changes until Apply and preserves applied props', () => {
		setup();
		const onApply = vi.fn();
		instance = mount(AdvancedRecipeSearch, { target, props: { open: true, filters, onApply } });
		flushSync();
		input('input', 'braise');
		expect(onApply).not.toHaveBeenCalled();
		expect(filters.rules[0].value).toBe('roast');
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		flushSync();
		expect(onApply).toHaveBeenCalledWith({
			...filters,
			rules: [{ field: 'method', operator: 'contains', value: 'braise' }]
		});
	});
	it('Cancel and Escape request dismissal without applying', () => {
		setup();
		const onApply = vi.fn();
		const onClose = vi.fn();
		instance = mount(AdvancedRecipeSearch, {
			target,
			props: { open: true, filters, onApply, onClose }
		});
		flushSync();
		input('input', 'braise');
		click('.cancel');
		target
			.querySelector('dialog')!
			.dispatchEvent(
				new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
			);
		flushSync();
		expect(onClose).toHaveBeenCalledTimes(2);
		expect(onApply).not.toHaveBeenCalled();
	});
	it('switches fields and operators without retaining incompatible values', () => {
		setup();
		instance = mount(AdvancedRecipeSearch, { target, props: { open: true, filters } });
		flushSync();
		input('select[aria-label="Field for rule 1"]', 'has_image', 'change');
		expect(target.querySelector('input')).toBeNull();
		expect(
			target.querySelector<HTMLSelectElement>('select[aria-label="Value for rule 1"]')!.value
		).toBe('true');
		input('select[aria-label="Field for rule 1"]', 'description', 'change');
		expect(target.querySelector<HTMLButtonElement>('.apply')!.disabled).toBe(true);
		input('select[aria-label="Operator for rule 1"]', 'is_empty', 'change');
		expect(target.querySelector('input')).toBeNull();
		expect(target.querySelector<HTMLButtonElement>('.apply')!.disabled).toBe(false);
	});
	it('keeps advanced-only search active and carries rules into result links', () => {
		setup();
		const onSearch = vi.fn();
		instance = mount(RecipesSearch, {
			target,
			props: {
				status: 'results',
				criteria: { filters },
				onSearch,
				results: {
					total: 1,
					facets: [],
					items: [
						{
							id: 'r1',
							name: 'Roast',
							book_id: 'b1',
							book_title: 'Book',
							book_author: 'Author',
							keywords: []
						}
					]
				}
			}
		});
		flushSync();
		expect(target.querySelector('[data-verify-active]')!.getAttribute('data-verify-active')).toBe(
			'true'
		);
		const href = target.querySelector('.rows .name')!.getAttribute('href')!;
		expect(new URL(href, 'http://example.test').searchParams.get('filters')).toBe(
			JSON.stringify(filters)
		);
		click('.applied-rules button');
		expect(onSearch.mock.calls[0][0].filters).toEqual(emptyFilters());
	});
});

describe('native dialog lifecycle', () => {
	it('opens modally, discards a draft on backdrop dismissal, restores focus, and reopens', async () => {
		setup();
		const original = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal');
		const showModal = vi.fn(function (this: HTMLDialogElement) {
			this.setAttribute('open', '');
		});
		Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
			value: showModal,
			configurable: true
		});
		try {
			const onSearch = vi.fn();
			instance = mount(RecipesSearch, { target, props: { criteria: { filters }, onSearch } });
			flushSync();
			click('.advanced-trigger');
			expect(showModal).toHaveBeenCalledTimes(1);
			input('dialog input', 'braise');
			click('dialog');
			await tick();
			flushSync();
			expect(target.querySelector('dialog')).toBeNull();
			await vi.waitFor(() =>
				expect(document.activeElement).toBe(target.querySelector('.advanced-trigger'))
			);
			expect(onSearch).not.toHaveBeenCalled();
			click('.advanced-trigger');
			expect(showModal).toHaveBeenCalledTimes(2);
			expect(target.querySelector<HTMLInputElement>('dialog input')!.value).toBe('roast');
		} finally {
			if (original) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', original);
			else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal');
		}
	});
});
