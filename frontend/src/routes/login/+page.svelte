<script lang="ts">
	import { goto } from '$app/navigation';
	import LoginForm from '$lib/components/LoginForm.svelte';
	import { login } from '$lib/api/auth';
	import { currentUser } from '$lib/auth';
	import { pageTitle } from '$lib/title';

	async function submit({ username, password }: { username: string; password: string }) {
		currentUser.set(await login(username, password));
		await goto('/');
	}
</script>

<svelte:head>
	<title>{pageTitle('Sign in')}</title>
</svelte:head>

<section class="page">
	<LoginForm onSubmit={submit} />
</section>

<style>
	.page {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}
</style>
