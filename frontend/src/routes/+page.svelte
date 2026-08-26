<script lang="ts">
	import { onMount } from 'svelte';
	import HomeLanding, {
		type BookOfTheDay,
		type ContinueBook,
		type ReadProgress,
		type RecentRecipe,
		type UpNextBook
	} from '$lib/components/HomeLanding.svelte';
	import { fetchHome } from '$lib/api/home';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let bookOfTheDay = $state<BookOfTheDay | null>(null);
	let progress = $state<ReadProgress>({ books: 0, booksRead: 0 });
	let continueReading = $state<ContinueBook[]>([]);
	let upNext = $state<UpNextBook[]>([]);
	let recentlyRead = $state<RecentRecipe[]>([]);

	async function load() {
		status = 'loading';
		try {
			const home = await fetchHome();
			const b = home.book_of_the_day;
			bookOfTheDay = b
				? {
						id: b.id,
						title: b.title,
						author: b.author,
						description: b.description,
						recipeCount: b.recipe_count,
						hasCover: b.has_cover
					}
				: null;
			progress = { books: home.stats.books, booksRead: home.stats.books_read };
			continueReading = home.continue_reading.map((c) => ({
				id: c.id,
				title: c.title,
				author: c.author,
				mode: c.mode,
				fraction: c.fraction,
				resumeRecipeId: c.resume_recipe_id,
				hasCover: c.has_cover
			}));
			upNext = home.up_next.map((b) => ({
				id: b.id,
				title: b.title,
				author: b.author,
				hasCover: b.has_cover,
				recipeCount: b.recipe_count
			}));
			recentlyRead = home.recently_read.map((r) => ({
				id: r.id,
				name: r.name,
				bookId: r.book_id,
				bookTitle: r.book_title
			}));
			status = 'ready';
		} catch (err) {
			console.error('failed to load home', err);
			status = 'error';
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle()}</title>
</svelte:head>

{#if status === 'ready'}
	<HomeLanding {bookOfTheDay} {progress} {continueReading} {upNext} {recentlyRead} />
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Loading…</p>
		{:else}
			<p class="msg">Couldn’t load the home page.</p>
			<button class="retry" onclick={load}>Try again</button>
		{/if}
	</div>
{/if}

<style>
	.status {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 5rem var(--page-h);
	}

	.msg {
		font-family: var(--f-serif);
		font-size: 1.4rem;
		color: var(--muted);
		margin: 0 0 1.2rem;
	}

	.retry {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		background: var(--ink);
		color: var(--bg);
		border: none;
		border-radius: 3px;
		padding: 0.55rem 1.1rem;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}

	.retry:hover {
		background: var(--accent-deep);
	}
</style>
