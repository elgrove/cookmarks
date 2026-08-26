<script module lang="ts">
	import type { ConversationSummary } from '$lib/api/assistant';

	export type AssistantChatProps = {
		conversations: ConversationSummary[];
		activeId: string | null;
		onNew?: () => void;
		onSelect?: (id: string) => void;
		onDelete?: (id: string) => void;
		/** Fired once a turn completes, so the rail can pick up a freshly-titled chat. */
		onTurnComplete?: () => void;
	};
</script>

<script lang="ts">
	import { Chat } from '@ai-sdk/svelte';
	import { DefaultChatTransport } from 'ai';
	import AssistantHistory from './AssistantHistory.svelte';
	import AssistantThread, { type ThreadMessage } from './AssistantThread.svelte';
	import { chatUrl, fetchConversation } from '$lib/api/assistant';

	let {
		conversations,
		activeId,
		onNew,
		onSelect,
		onDelete,
		onTurnComplete
	}: AssistantChatProps = $props();

	let unavailable = $state(false);
	let error = $state<string | null>(null);
	let chat = $state<Chat | null>(null);

	// A Chat is bound to one conversation's endpoint, so switching conversations builds
	// a new one, seeded with the history the server replayed.
	$effect(() => {
		const id = activeId;
		if (!id) {
			chat = null;
			return;
		}
		let stale = false;
		unavailable = false;
		error = null;
		fetchConversation(id)
			.then((conversation) => {
				if (stale) return;
				chat = new Chat({
					id,
					messages: conversation.messages as never[],
					transport: new DefaultChatTransport({ api: chatUrl(id) }),
					onError: (err) => {
						// The chat endpoint answers 409 when no provider is configured; that is a
						// setup state to explain, not a failure to apologise for.
						unavailable = /409/.test(err.message);
						error = unavailable ? null : 'The assistant could not finish that answer.';
					},
					onFinish: () => onTurnComplete?.()
				});
			})
			.catch((err) => {
				console.error('failed to load the conversation', err);
				error = 'Could not load that conversation.';
			});
		return () => {
			stale = true;
		};
	});

	let messages = $derived((chat?.messages ?? []) as ThreadMessage[]);
	let status = $derived(chat?.status ?? 'ready');

	function send(text: string) {
		error = null;
		chat?.sendMessage({ text });
	}
</script>

<div class="assistant">
	<aside class="rail">
		<AssistantHistory {conversations} {activeId} {onNew} {onSelect} {onDelete} />
	</aside>
	<div class="pane">
		<AssistantThread {messages} {status} {unavailable} {error} onSend={send} />
	</div>
</div>

<style>
	.assistant {
		display: grid;
		grid-template-columns: 15rem 1fr;
		gap: var(--col-gap);
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 2rem;
		align-items: start;
	}

	.rail {
		position: sticky;
		top: var(--page-pt);
	}

	.pane {
		min-width: 0;
	}

	@media (max-width: 900px) {
		.assistant {
			grid-template-columns: 1fr;
			gap: 2rem;
		}
		.rail {
			position: static;
		}
	}
</style>
