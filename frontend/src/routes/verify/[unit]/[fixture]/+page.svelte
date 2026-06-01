<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { setCurrent } from '$lib/verify/handle';
	import { getUnit } from '$lib/verify/registry';
	import { runFixture } from '$lib/verify/runner';
	import type { VerifyResult } from '$lib/verify/types';

	const unitId = $page.params.unit ?? '';
	const fixtureId = $page.params.fixture ?? '';
	const unit = getUnit(unitId);
	const fixture = unit?.fixtures.find((f) => f.id === fixtureId);

	let target = $state<HTMLElement>();
	let result = $state<VerifyResult | null>(null);

	// Verify the *visible* instance: runFixture mounts the component into this
	// on-screen node and applies `act` to it, so the screenshot an agent takes
	// always matches the verdict it scrapes (no parallel hidden copy).
	onMount(async () => {
		if (unit && fixture && target) {
			result = await runFixture(unit, fixture, { target, keepMounted: true });
			setCurrent(result);
		}
	});
</script>

{#if unit && fixture}
	<div bind:this={target} data-verify-target></div>
	{#if result}
		<p
			data-verify-verdict={result.verdict}
			style={`color: var(--${result.verdict.toLowerCase()}); font-weight: 600`}
		>
			{result.verdict}
		</p>
	{/if}
{:else}
	<p>Unknown unit/fixture: {unitId}/{fixtureId}</p>
{/if}
