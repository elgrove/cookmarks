<script lang="ts">
	// Placeholder component existing only to exercise the harness.
	// Delete it (and _smoke.verify.ts) once the first real unit lands.
	let { label = 'smoke', broken = false }: { label?: string; broken?: boolean } = $props();
	let count = $derived(broken ? 999 : 1);
</script>

<article data-verify-unit="smoke" data-verify-label={label} data-verify-count={count}>
	<h1>{label}</h1>
	<p data-verify-role="count">{count} item</p>
	<button aria-label="acknowledge">ok</button>
</article>
