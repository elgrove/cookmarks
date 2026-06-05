<script lang="ts">
	import { onMount } from 'svelte';
	import { buildManifest, runAll } from '$lib/verify/runner';
	import type { Verdict, VerifyResult } from '$lib/verify/types';
	import { pageTitle } from '$lib/title';

	let results = $state<VerifyResult[]>([]);
	let running = $state(true);
	const manifest = buildManifest();

	async function run() {
		running = true;
		results = await runAll();
		running = false;
	}

	onMount(run);

	const summary = $derived.by(() => {
		const counts: Record<Verdict, number> = { PASS: 0, FAIL: 0, BLOCKED: 0, SKIP: 0 };
		for (const r of results) counts[r.verdict]++;
		return counts;
	});

	function failLabels(r: VerifyResult): string {
		return r.checks
			.filter((c) => c.status === 'fail')
			.map((c) => `${c.label}${c.detail ? ` (${c.detail})` : ''}`)
			.join('; ');
	}
</script>

<svelte:head>
	<title>{pageTitle('Verify')}</title>
</svelte:head>

<h1>Verification</h1>

<p>
	{manifest.length} fixtures ·
	<span style="color: var(--pass)">{summary.PASS} pass</span> ·
	<span style="color: var(--fail)">{summary.FAIL} fail</span> ·
	<span style="color: var(--blocked)">{summary.BLOCKED} blocked</span> ·
	<span style="color: var(--skip)">{summary.SKIP} skip</span>
</p>

<button onclick={run} disabled={running}>{running ? 'Running…' : 'Run all'}</button>

<table data-verify-dashboard>
	<thead>
		<tr><th>Unit</th><th>Fixture</th><th>Verdict</th><th>Failing checks</th></tr>
	</thead>
	<tbody>
		{#each results as r (r.unitId + '/' + r.fixtureId)}
			<tr>
				<td>{r.unitId}</td>
				<td><a href={`/verify/${r.unitId}/${r.fixtureId}`}>{r.fixtureId}</a></td>
				<td style={`color: var(--${r.verdict.toLowerCase()}); font-weight: 600`}>{r.verdict}</td>
				<td>{failLabels(r)}</td>
			</tr>
		{/each}
	</tbody>
</table>
