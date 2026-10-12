// MY-178: the list-detail route refetched /api/lists/{id} in an endless loop.
// The route effect read `list` before its first await and wrote it after, so
// Svelte tracked `list` as a dependency and every response re-triggered the
// effect (4,310 requests and 37 MB in one production audit). This mounts the
// real route and proves one route id causes exactly one detail fetch.
import { mount, unmount, tick } from 'svelte';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import ListPage from './+page.svelte';
import { setPageId } from '../../../test-mocks/app-stores';

const LIST_A = '11111111-1111-4111-8111-111111111111';
const LIST_B = '22222222-2222-4222-8222-222222222222';

function detailPayload(id: string, name: string): object {
	return {
		id,
		name,
		is_default: false,
		recipe_count: 1,
		recipes: [
			{
				id: '33333333-3333-4333-8333-333333333333',
				name: 'Soup',
				book_id: '44444444-4444-4444-8444-444444444444',
				book_title: 'Book',
				book_author: 'Author',
				keywords: []
			}
		]
	};
}

// Flush pending promises and Svelte effects a bounded number of times. A
// looping loader keeps fetching on every flush, so the call count tells the
// fixed and broken versions apart without hanging the suite.
async function settle(rounds = 30): Promise<void> {
	for (let i = 0; i < rounds; i++) {
		await Promise.resolve();
		await tick();
	}
}

describe('lists/[id] route loader', () => {
	const detailCalls: string[] = [];
	let mounted: object | null = null;

	beforeEach(() => {
		detailCalls.length = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn(async (input: unknown) => {
				const url = String(input);
				if (url === '/api/lists') return Response.json([]);
				const match = url.match(/^\/api\/lists\/([^/]+)$/);
				if (match) {
					detailCalls.push(match[1]);
					return Response.json(detailPayload(match[1], `List ${match[1].slice(0, 4)}`));
				}
				return Response.json({}, { status: 404 });
			})
		);
		setPageId(LIST_A);
		const target = document.createElement('div');
		document.body.appendChild(target);
		mounted = mount(ListPage, { target });
	});

	afterEach(async () => {
		if (mounted) await unmount(mounted);
		mounted = null;
		document.body.innerHTML = '';
		vi.unstubAllGlobals();
	});

	it('fetches the list exactly once per route id', async () => {
		await settle();
		expect(detailCalls.filter((id) => id === LIST_A)).toHaveLength(1);

		setPageId(LIST_B);
		await settle();
		expect(detailCalls.filter((id) => id === LIST_B)).toHaveLength(1);
		expect(detailCalls).toHaveLength(2);
	});
});
