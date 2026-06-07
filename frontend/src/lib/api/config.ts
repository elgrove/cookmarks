import { z } from 'zod';

// The AI providers the backend knows about (mirrors app.models.enums.AIProvider).
export const aiProviderSchema = z.enum(['GEMINI', 'OPENROUTER', 'STUB']);
export type AiProvider = z.infer<typeof aiProviderSchema>;

const providerInfoSchema = z.object({
	name: aiProviderSchema,
	requires_api_key: z.boolean()
});

// Mirrors the ConfigRead wire shape from GET/PATCH /api/config (snake_case). The API
// key itself is never sent over the wire — only `api_key_set` tells us whether one is stored.
export const configSchema = z.object({
	ai_provider: aiProviderSchema.nullable(),
	api_key_set: z.boolean(),
	extraction_rate_limit_per_minute: z.number().int().positive(),
	providers: z.array(providerInfoSchema)
});

export type Config = z.infer<typeof configSchema>;
export type ProviderInfo = z.infer<typeof providerInfoSchema>;

// A partial update (mirrors ConfigUpdate). Only the fields present are applied; for
// `api_key`, an empty string or null clears the stored key, a non-empty string sets it.
export type ConfigUpdate = {
	ai_provider?: AiProvider | null;
	api_key?: string | null;
	extraction_rate_limit_per_minute?: number;
};

/** Fetch and validate the current settings. `fetchFn` is injectable for SSR/tests. */
export async function fetchConfig(fetchFn: typeof fetch = fetch): Promise<Config> {
	const res = await fetchFn('/api/config');
	if (!res.ok) throw new Error(`GET /api/config → ${res.status}`);
	return configSchema.parse(await res.json());
}

/** Apply a partial settings update and return the refreshed (key-free) config. */
export async function updateConfig(
	patch: ConfigUpdate,
	fetchFn: typeof fetch = fetch
): Promise<Config> {
	const res = await fetchFn('/api/config', {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(patch)
	});
	if (!res.ok) throw new Error(`PATCH /api/config → ${res.status}`);
	return configSchema.parse(await res.json());
}
