<script lang="ts">
	type Theme = 'light' | 'dark';

	let { theme = 'light', onToggle }: { theme?: Theme; onToggle?: () => void } = $props();

	// Name the *action*, not the state, so the control is self-describing (DESIGN §8).
	const label = $derived(theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
</script>

<button
	class="theme-toggle"
	type="button"
	data-verify-unit="theme-toggle"
	data-verify-theme={theme}
	aria-label={label}
	aria-pressed={theme === 'dark'}
	title={label}
	onclick={() => onToggle?.()}
>
	{#if theme === 'dark'}
		<!-- moon: dark is active, click returns to light -->
		<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
			<path
				d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		</svg>
	{:else}
		<!-- sun: light is active, click switches to dark -->
		<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
			<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
				<circle cx="12" cy="12" r="4" />
				<path
					d="M12 2v2.5M12 19.5V22M22 12h-2.5M4.5 12H2M19.07 4.93l-1.77 1.77M6.7 17.3l-1.77 1.77M19.07 19.07l-1.77-1.77M6.7 6.7L4.93 4.93"
				/>
			</g>
		</svg>
	{/if}
</button>

<style>
	.theme-toggle {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		padding: 0;
		background: transparent;
		border: none;
		border-radius: 4px;
		color: var(--muted);
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}

	.theme-toggle:hover {
		color: var(--ink);
	}
</style>
