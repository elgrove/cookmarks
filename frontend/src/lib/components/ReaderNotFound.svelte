<script module lang="ts">
	export type ReaderNotFoundProps = {
		/** The recipe's name when known — a targeted id can be absent from the book's
		 *  recipe index entirely, in which case the copy falls back to "this recipe". */
		recipeName: string | null;
		/** The way back to the recipe page the jump came from. */
		recipeHref: string;
		onOpenAtStart?: () => void;
	};
</script>

<script lang="ts">
	let { recipeName, recipeHref, onOpenAtStart }: ReaderNotFoundProps = $props();

	// Echo of the last action, so the harness can verify wiring without a reader behind it.
	let lastAction = $state('');

	function openAtStart() {
		lastAction = 'open-at-start';
		onOpenAtStart?.();
	}
</script>

<div
	class="notfound"
	data-verify-unit="reader-not-found"
	data-verify-recipe-name={recipeName ?? ''}
	data-verify-recipe-href={recipeHref}
	data-verify-action={lastAction}
>
	<p class="msg">
		{#if recipeName}
			Couldn’t find “{recipeName}” in this book’s pages.
		{:else}
			Couldn’t find this recipe in this book’s pages.
		{/if}
	</p>
	<p class="hint">The book may spell its title differently.</p>
	<div class="choices">
		<button class="start" type="button" onclick={openAtStart}>Open at the start</button>
		<a class="back" href={recipeHref}>← Back to the recipe</a>
	</div>
</div>

<style>
	.notfound {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 2rem;
		text-align: center;
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--ink);
		margin: 0;
		max-width: 34rem;
		overflow-wrap: break-word;
	}
	.hint {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--muted);
		margin: 0;
	}
	.choices {
		display: flex;
		align-items: center;
		gap: 1.5rem;
		margin-top: 1.1rem;
	}
	.start {
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
	.start:hover {
		background: var(--clay-deep);
	}
	.back {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		color: var(--clay-deep);
		text-decoration: none;
		border-bottom: 1px solid transparent;
	}
	.back:hover {
		border-bottom-color: var(--clay);
	}
</style>
