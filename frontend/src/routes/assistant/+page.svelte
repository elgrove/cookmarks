<script lang="ts">
	import { onMount } from 'svelte';
	import AssistantChat from '$lib/components/AssistantChat.svelte';
	import {
		createConversation,
		deleteConversation,
		fetchConversations,
		type ConversationSummary
	} from '$lib/api/assistant';
	import { pageTitle } from '$lib/title';

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let conversations = $state<ConversationSummary[]>([]);
	let activeId = $state<string | null>(null);

	async function load() {
		status = 'loading';
		try {
			conversations = await fetchConversations();
			if (conversations.length === 0) {
				await start();
			} else if (!activeId || !conversations.some((c) => c.id === activeId)) {
				activeId = conversations[0].id;
			}
			status = 'ready';
		} catch (err) {
			console.error('failed to load conversations', err);
			status = 'error';
		}
	}

	async function start() {
		const created = await createConversation();
		conversations = [created, ...conversations];
		activeId = created.id;
	}

	async function newChat() {
		try {
			await start();
		} catch (err) {
			console.error('failed to start a conversation', err);
		}
	}

	async function remove(id: string) {
		try {
			await deleteConversation(id);
			conversations = conversations.filter((c) => c.id !== id);
			if (activeId === id) activeId = conversations[0]?.id ?? null;
			if (!activeId) await start();
		} catch (err) {
			console.error('failed to delete the conversation', err);
		}
	}

	// A first turn gives an untitled conversation its name, so re-read the rail.
	async function refreshTitles() {
		try {
			conversations = await fetchConversations();
		} catch (err) {
			console.error('failed to refresh conversations', err);
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle('Assistant')}</title>
</svelte:head>

{#if status === 'ready'}
	<AssistantChat
		{conversations}
		{activeId}
		onNew={newChat}
		onSelect={(id) => (activeId = id)}
		onDelete={remove}
		onTurnComplete={refreshTitles}
	/>
{:else}
	<div class="status">
		{#if status === 'loading'}
			<p class="msg">Waking the assistant…</p>
		{:else}
			<p class="msg">Couldn’t reach the assistant.</p>
			<button class="retry" onclick={load}>Try again</button>
		{/if}
	</div>
{/if}

<style>
	.status {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 4rem var(--page-h);
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.4rem;
		color: var(--muted);
		margin: 0.5rem 0 1.2rem;
	}
	.retry {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		background: var(--ink);
		color: var(--bg);
		border: none;
		border-radius: 3px;
		padding: 0.55rem 1.1rem;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}
	.retry:hover {
		background: var(--clay-deep);
	}
</style>
