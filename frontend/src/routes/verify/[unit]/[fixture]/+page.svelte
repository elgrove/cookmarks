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
	const Component = unit?.component;

	let result = $state<VerifyResult | null>(null);

	onMount(async () => {
		if (unit && fixture) {
			result = await runFixture(unit, fixture);
			setCurrent(result);
		}
	});
</script>

{#if unit && fixture && Component}
	<div data-verify-target>
		<Component {...fixture.props} />
	</div>
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
