<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { installVerifyHandle } from '$lib/verify/handle';
	import '../app.css';

	let { children } = $props();

	onMount(installVerifyHandle);
</script>

{#if $page.url.searchParams.get('chrome') !== '0'}
	<nav class="nav">
		<a href="/">Cookmarks</a>
	</nav>
{/if}

<main>
	{@render children()}
</main>
