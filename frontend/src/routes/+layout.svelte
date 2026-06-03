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
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { initTheme, resolvedTheme, toggleTheme } from '$lib/theme';
	import '../app.css';

	let { children } = $props();

	onMount(installVerifyHandle);
	onMount(initTheme);

	// The EPUB reader is an immersive, full-viewport view with its own chrome — suppress the
	// global nav/footer there (as the verify harness already does via ?chrome=0).
	let showChrome = $derived(
		$page.url.searchParams.get('chrome') !== '0' && !$page.url.pathname.endsWith('/read')
	);
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
		<ThemeToggle theme={$resolvedTheme} onToggle={toggleTheme} />
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
