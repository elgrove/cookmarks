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
	import { initTheme } from '$lib/theme';
	import { fetchTicketsEnabled, submitTicket } from '$lib/api/tickets';
	import TicketModal from '$lib/components/TicketModal.svelte';
	import '../app.css';

	let { children } = $props();

	onMount(installVerifyHandle);
	onMount(initTheme);

	// The footer "Submit a ticket" link only appears when the backend's Linear
	// integration is configured; the modal files the issue via POST /api/tickets.
	let ticketsEnabled = $state(false);
	let ticketOpen = $state(false);
	onMount(async () => {
		try {
			ticketsEnabled = await fetchTicketsEnabled();
		} catch {
			ticketsEnabled = false;
		}
	});

	// The EPUB reader is an immersive, full-viewport view with its own chrome — suppress the
	// global nav/footer there (as the verify harness already does via ?chrome=0).
	let showChrome = $derived(
		$page.url.searchParams.get('chrome') !== '0' && !$page.url.pathname.endsWith('/read')
	);
</script>

{#if showChrome}
	<nav class="nav">
		<a class="wordmark" href="/">Cookmarks</a>
		<a class="navlink" class:active={$page.url.pathname.startsWith('/books')} href="/books">Books</a>
		<a
			class="navlink"
			class:active={$page.url.pathname.startsWith('/recipes')}
			href="/recipes">Recipes</a
		>
		<a
			class="navlink"
			class:active={$page.url.pathname.startsWith('/lists')}
			href="/lists">Lists</a
		>
		<a
			class="admin-icon"
			class:active={$page.url.pathname.startsWith('/admin')}
			href="/admin"
			aria-label="Admin"
			title="Admin"
		>
			<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
				<circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.8" />
				<path
					d="M4 20c0-4 3.6-7 8-7s8 3 8 7"
					fill="none"
					stroke="currentColor"
					stroke-width="1.8"
					stroke-linecap="round"
				/>
			</svg>
		</a>
	</nav>
{/if}

<main>
	{@render children()}
</main>

{#if showChrome}
	<footer class="foot">
		<span class="foot-mark">Cookmarks</span>
		{#if ticketsEnabled}
			<button class="foot-ticket" type="button" onclick={() => (ticketOpen = true)}>
				Submit a ticket
			</button>
		{/if}
	</footer>

	{#if ticketsEnabled}
		<TicketModal bind:open={ticketOpen} onSubmit={submitTicket} />
	{/if}
{/if}
