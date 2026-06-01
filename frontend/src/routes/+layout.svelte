<script lang="ts">
	import '@fontsource-variable/source-serif-4';
	import '@fontsource-variable/source-serif-4/wght-italic.css';
	import '@fontsource/schibsted-grotesk/400.css';
	import '@fontsource/schibsted-grotesk/500.css';
	import '@fontsource/schibsted-grotesk/600.css';
	import '@fontsource/schibsted-grotesk/700.css';
	import '@fontsource/ibm-plex-mono/300.css';
	import '@fontsource/ibm-plex-mono/400.css';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { installVerifyHandle } from '$lib/verify/handle';
	import '../app.css';

	let { children } = $props();

	onMount(installVerifyHandle);

	let showChrome = $derived($page.url.searchParams.get('chrome') !== '0');
</script>

{#if showChrome}
	<nav class="nav">
		<a class="wordmark" href="/">Cookmarks</a>
		<a class="navlink" class:active={$page.url.pathname === '/'} href="/">Home</a>
		<a class="navlink" class:active={$page.url.pathname.startsWith('/books')} href="/books">Books</a>
		<a
			class="navlink"
			class:active={$page.url.pathname.startsWith('/recipes')}
			href="/recipes">Recipes</a
		>
	</nav>
{/if}

<main>
	{@render children()}
</main>

{#if showChrome}
	<footer class="foot">
		<span class="foot-mark">Cookmarks</span>
		<span class="foot-note mono">Personal recipe archive · self-hosted</span>
	</footer>
{/if}
