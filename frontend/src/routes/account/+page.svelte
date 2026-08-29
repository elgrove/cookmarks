<script lang="ts">
	import AccountSettings from '$lib/components/AccountSettings.svelte';
	import { updateMe } from '$lib/api/auth';
	import { currentUser } from '$lib/auth';
	import { pageTitle } from '$lib/title';

	$effect(() => {
		pageTitle('Account');
	});

	async function handleSave(instructions: string | null) {
		const updated = await updateMe({ cooking_instructions: instructions });
		currentUser.set(updated);
	}
</script>

{#if $currentUser}
	<AccountSettings
		username={$currentUser.username}
		instructions={$currentUser.cooking_instructions ?? null}
		onSave={handleSave}
	/>
{/if}
