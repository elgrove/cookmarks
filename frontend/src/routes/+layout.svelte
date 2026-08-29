<script lang="ts">
	import '@fontsource/space-grotesk/400.css';
	import '@fontsource/space-grotesk/500.css';
	import '@fontsource/space-grotesk/600.css';
	import '@fontsource/space-grotesk/700.css';
	import '@fontsource/ibm-plex-mono/400.css';
	import '@fontsource/ibm-plex-mono/500.css';
	import '@fontsource/ibm-plex-mono/600.css';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { installVerifyHandle } from '$lib/verify/handle';
	import { initTheme } from '$lib/theme';
	import { fetchTicketsEnabled, submitTicket } from '$lib/api/tickets';
	import { fetchMe, logout } from '$lib/api/auth';
	import { currentUser } from '$lib/auth';
	import TicketModal from '$lib/components/TicketModal.svelte';
	import '../app.css';

	let { children } = $props();

	onMount(installVerifyHandle);
	onMount(initTheme);

	// The session gate. /login and the verify harness are exempt — the harness mounts
	// components against fixture props and must stay reachable without an account.
	let loginRoute = $derived($page.url.pathname === '/login');
	let openRoute = $derived(loginRoute || $page.url.pathname.startsWith('/verify'));

	// Pages stay unmounted until the session resolves, so a signed-out visitor never
	// sees a protected page fire its fetches and settle on an error before redirecting.
	let sessionResolved = $state(false);
	onMount(async () => {
		if (openRoute) {
			sessionResolved = true;
			return;
		}
		try {
			const me = await fetchMe();
			currentUser.set(me);
			if (!me) await goto('/login');
		} catch (err) {
			console.error('failed to resolve the session', err);
		}
		sessionResolved = true;
	});

	// A deployment running COOKMARKS_AUTH_MODE=none has no accounts to show.
	let showAccount = $derived(!!$currentUser && $currentUser.auth_mode !== 'none');

	async function signOut() {
		try {
			await logout();
		} catch (err) {
			console.error('failed to sign out', err);
		}
		currentUser.set(null);
		await goto('/login');
	}

	// The footer "Submit a ticket" link only appears when the backend's Linear
	// integration is configured; the modal files the issue via POST /api/tickets.
	let ticketsEnabled = $state(false);
	let ticketOpen = $state(false);
	// The flag itself sits behind the session gate, so ask only once signed in.
	$effect(() => {
		if (!$currentUser) {
			ticketsEnabled = false;
			return;
		}
		fetchTicketsEnabled()
			.then((enabled) => (ticketsEnabled = enabled))
			.catch(() => (ticketsEnabled = false));
	});

	// The EPUB reader is an immersive, full-viewport view with its own chrome — suppress the
	// global nav/footer there (as the verify harness already does via ?chrome=0). The sign-in
	// screen drops it too: its nav would only link to pages the visitor can't reach yet.
	let showChrome = $derived(
		$page.url.searchParams.get('chrome') !== '0' &&
			!$page.url.pathname.endsWith('/read') &&
			!loginRoute
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
			class="navlink"
			class:active={$page.url.pathname.startsWith('/assistant')}
			href="/assistant">Assistant</a
		>
		{#if $currentUser?.is_admin}
			<a
				class="navlink"
				class:active={$page.url.pathname.startsWith('/add')}
				href="/add">Add</a
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
		{/if}
		{#if showAccount}
			<span class="who">{$currentUser?.username}</span>
			<button class="signout" type="button" onclick={signOut}>Sign out</button>
		{/if}
	</nav>
{/if}

<main>
	{#if sessionResolved}
		{@render children()}
	{/if}
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
