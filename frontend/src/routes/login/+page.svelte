<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import LoginForm from '$lib/components/LoginForm.svelte';
	import { fetchMe, login } from '$lib/api/auth';
	import { currentUser } from '$lib/auth';
	import { pageTitle } from '$lib/title';

	// Already signed in (or a deployment with accounts turned off): nothing to do here.
	onMount(async () => {
		const me = await fetchMe().catch(() => null);
		if (!me) return;
		currentUser.set(me);
		await goto('/');
	});

	async function submit({ username, password }: { username: string; password: string }) {
		currentUser.set(await login(username, password));
		await goto('/');
	}
</script>

<svelte:head>
	<title>{pageTitle('Sign in')}</title>
</svelte:head>

<section class="page">
	<div class="form">
		<LoginForm onSubmit={submit} />
	</div>

	<!-- A typographic plate rather than an image: the same treatment the app gives an
	     imageless recipe (DESIGN §7). -->
	<aside class="plate" aria-hidden="true">
		<span class="initial">C</span>
		<p class="line">A private index of everything worth cooking from the shelf.</p>
	</aside>
</section>

<style>
	.page {
		display: grid;
		grid-template-columns: minmax(0, 26rem) minmax(0, 1fr);
		gap: clamp(2rem, 8vw, 7rem);
		align-items: center;
		min-height: 100vh;
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 3rem var(--page-h);
	}
	.form {
		/* Nudged off centre — the page reads as a composition, not a centred box. */
		padding-bottom: 4rem;
	}
	.plate {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		min-height: 22rem;
		padding: 2.5rem;
		background: var(--bg-warm);
		border: var(--border);
		border-radius: 2px;
		overflow: hidden;
	}
	.initial {
		position: absolute;
		top: -2.5rem;
		left: 1rem;
		font-family: var(--f-serif);
		font-style: italic;
		font-weight: 300;
		font-size: 20rem;
		line-height: 1;
		color: var(--clay);
		opacity: 0.16;
		user-select: none;
	}
	.line {
		position: relative;
		font-family: var(--f-serif);
		font-style: italic;
		font-size: clamp(1.2rem, 2.4vw, 1.7rem);
		line-height: 1.35;
		color: var(--muted);
		margin: 0;
		max-width: 22rem;
	}
	@media (max-width: 900px) {
		.page {
			grid-template-columns: 1fr;
			align-items: start;
			gap: 2.5rem;
			padding-top: var(--page-pt);
			min-height: 0;
		}
		.form {
			padding-bottom: 0;
		}
		.plate {
			display: none;
		}
	}
</style>
