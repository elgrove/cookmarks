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
</section>

<style>
	.page {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		padding: 3rem var(--page-h);
	}
	.form {
		width: 100%;
		max-width: 26rem;
	}
	@media (max-width: 900px) {
		.page {
			align-items: start;
			padding-top: var(--page-pt);
			min-height: 0;
		}
	}
</style>
