<script module lang="ts">
	export type FavouriteToggleProps = {
		isFavourite: boolean;
		/** The recipe's name, woven into the accessible label. */
		recipeName?: string;
		onToggle?: () => void;
	};
</script>

<script lang="ts">
	let { isFavourite, recipeName = '', onToggle }: FavouriteToggleProps = $props();

	// Local echo of a click, so the harness can verify the handler fired even though
	// the parent owns `isFavourite` and won't change it in isolation.
	let clicked = $state(false);

	let label = $derived(
		`${isFavourite ? 'Remove' : 'Add'} ${recipeName ? `“${recipeName}” ` : ''}${
			isFavourite ? 'from' : 'to'
		} favourites`
	);

	function toggle() {
		clicked = true;
		onToggle?.();
	}
</script>

<button
	class="fav"
	class:on={isFavourite}
	type="button"
	data-verify-unit="favourite-toggle"
	data-verify-favourite={isFavourite ? 'true' : 'false'}
	data-verify-clicked={clicked ? 'true' : 'false'}
	aria-pressed={isFavourite}
	aria-label={label}
	onclick={toggle}
>
	<span class="star" aria-hidden="true">{isFavourite ? '★' : '☆'}</span>
	<span class="text">{isFavourite ? 'Favourited' : 'Favourite'}</span>
</button>

<style>
	.fav {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		padding: 0.7rem 1rem;
		background: var(--card);
		color: var(--ink);
		border: 1px solid var(--ink);
		cursor: pointer;
		transition:
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.fav:hover {
		border-color: var(--accent);
		color: var(--accent-deep);
	}
	.fav.on {
		border-color: var(--accent);
		color: var(--accent-deep);
	}
	.star {
		font-size: 1rem;
		line-height: 1;
		color: var(--accent);
	}
</style>
