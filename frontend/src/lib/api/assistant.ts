import { z } from 'zod';

// Mirrors the /api/assistant wire shapes. The message `parts` are the Vercel AI SDK's
// own UIMessage parts — library-owned on both ends, so they stay permissive here and
// are narrowed at render time by `type`.
export const assistantMessageSchema = z.object({
	id: z.string(),
	role: z.enum(['system', 'user', 'assistant']),
	parts: z.array(z.object({ type: z.string() }).passthrough())
});

export const conversationSummarySchema = z.object({
	id: z.string().uuid(),
	title: z.string().nullable(),
	created_at: z.string(),
	updated_at: z.string()
});

export const conversationDetailSchema = conversationSummarySchema.extend({
	messages: z.array(assistantMessageSchema)
});

export const conversationsResponseSchema = z.array(conversationSummarySchema);

export type AssistantMessage = z.infer<typeof assistantMessageSchema>;
export type ConversationSummary = z.infer<typeof conversationSummarySchema>;
export type ConversationDetail = z.infer<typeof conversationDetailSchema>;

/** The chat stream endpoint the `Chat` transport posts to. */
export const chatUrl = (id: string) => `/api/assistant/conversations/${id}/chat`;

export async function fetchConversations(
	fetchFn: typeof fetch = fetch
): Promise<ConversationSummary[]> {
	const res = await fetchFn('/api/assistant/conversations');
	if (!res.ok) throw new Error(`GET /api/assistant/conversations → ${res.status}`);
	return conversationsResponseSchema.parse(await res.json());
}

export async function createConversation(
	fetchFn: typeof fetch = fetch
): Promise<ConversationSummary> {
	const res = await fetchFn('/api/assistant/conversations', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/assistant/conversations → ${res.status}`);
	return conversationSummarySchema.parse(await res.json());
}

/** One conversation with its stored turns replayed as UI messages. */
export async function fetchConversation(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<ConversationDetail> {
	const res = await fetchFn(`/api/assistant/conversations/${id}`);
	if (!res.ok) throw new Error(`GET /api/assistant/conversations/${id} → ${res.status}`);
	return conversationDetailSchema.parse(await res.json());
}

export async function deleteConversation(
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/assistant/conversations/${id}`, { method: 'DELETE' });
	if (!res.ok) throw new Error(`DELETE /api/assistant/conversations/${id} → ${res.status}`);
}
