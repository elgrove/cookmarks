<script module lang="ts">
	export type AdminTab = { id: string; label: string };
	export type AdminTabsProps = {
		tabs: AdminTab[];
		active: string;
		onSelect?: (id: string) => void;
	};
</script>

<script lang="ts">
	let { tabs, active, onSelect }: AdminTabsProps = $props();
</script>

<div class="tabs" role="tablist" aria-label="Admin sections">
	{#each tabs as tab (tab.id)}
		<button
			class="tab"
			class:active={tab.id === active}
			role="tab"
			type="button"
			aria-selected={tab.id === active}
			onclick={() => onSelect?.(tab.id)}
		>
			{tab.label}
		</button>
	{/each}
</div>

<style>
	.tabs {
		display: flex;
		gap: 1.5rem;
		border-bottom: var(--border);
		margin-bottom: 2.5rem;
	}
	.tab {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--muted);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		padding: 0 0 0.7rem;
		margin-bottom: -1px;
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}
	.tab:hover {
		color: var(--ink);
	}
	.tab.active {
		color: var(--ink);
		border-bottom-color: var(--accent);
	}
</style>
