<script module lang="ts">
	import type { ConversationSummary } from '$lib/api/assistant';

	export type AssistantHistoryProps = {
		conversations: ConversationSummary[];
		activeId?: string | null;
		onSelect?: (id: string) => void;
		onNew?: () => void;
		onDelete?: (id: string) => void;
	};
</script>

<script lang="ts">
	let { conversations, activeId = null, onSelect, onNew, onDelete }: AssistantHistoryProps =
		$props();

	let lastDeleted = $state('');

	function label(conversation: ConversationSummary): string {
		return conversation.title?.trim() || 'Untitled';
	}

	function remove(id: string) {
		lastDeleted = id;
		onDelete?.(id);
	}
</script>

<nav
	class="history"
	aria-label="Past conversations"
	data-verify-unit="assistant-history"
	data-verify-count={conversations.length}
	data-verify-empty={conversations.length === 0 ? 'true' : 'false'}
	data-verify-active={activeId ?? ''}
	data-verify-first={conversations[0] ? label(conversations[0]) : ''}
	data-verify-deleted={lastDeleted}
>
	<div class="head">
		<p class="label">Conversations</p>
		<button class="new" type="button" onclick={() => onNew?.()}>New</button>
	</div>

	{#if conversations.length === 0}
		<p class="empty">Nothing asked yet.</p>
	{:else}
		<ul class="items">
			{#each conversations as conversation (conversation.id)}
				<li class="item" class:active={conversation.id === activeId}>
					<button
						class="open"
						type="button"
						aria-current={conversation.id === activeId ? 'true' : undefined}
						onclick={() => onSelect?.(conversation.id)}
					>
						{label(conversation)}
					</button>
					<button
						class="remove"
						type="button"
						aria-label={`Delete conversation: ${label(conversation)}`}
						onclick={() => remove(conversation.id)}
					>
						×
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</nav>

<style>
	.history {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		border-bottom: var(--border-strong);
		padding-bottom: 0.5rem;
	}

	.new {
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.75rem;
		background: none;
		border: var(--border);
		border-radius: 3px;
		color: var(--ink);
		padding: 0.25rem 0.7rem;
		cursor: pointer;
		transition: border-color 0.18s var(--ease-out);
	}

	.new:hover {
		border-color: var(--clay);
	}

	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		color: var(--faint);
		margin: 0;
	}

	.items {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border-bottom: var(--border);
	}

	.open {
		flex: 1;
		min-width: 0;
		text-align: left;
		font-family: var(--f-serif);
		font-size: 0.95rem;
		color: var(--muted);
		background: none;
		border: none;
		padding: 0.55rem 0;
		cursor: pointer;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		transition: color 0.18s var(--ease-out);
	}

	.open:hover {
		color: var(--ink);
	}

	.item.active .open {
		color: var(--ink);
		font-style: italic;
	}

	.item.active {
		border-left: 2px solid var(--clay);
		padding-left: 0.6rem;
	}

	.remove {
		flex: none;
		font-family: var(--f-grotesk);
		font-size: 1rem;
		line-height: 1;
		color: var(--faint);
		background: none;
		border: none;
		padding: 0.2rem 0.35rem;
		cursor: pointer;
	}

	.remove:hover {
		color: var(--clay-deep);
	}
</style>
