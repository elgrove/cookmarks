import { z } from 'zod';

// The AI providers the backend knows about (mirrors app.models.enums.AIProvider).
// STUB is the offline test provider: never user-configurable, so it stays out of
// the settings wire shapes.
export const aiProviderSchema = z.enum(['ANTHROPIC', 'GEMINI', 'OPENROUTER']);
export type AiProvider = z.infer<typeof aiProviderSchema>;

// Task roles (mirrors app.models.enums.ModelRole).
export const modelRoleSchema = z.enum([
	'image_match',
	'ocr',
	'many_recipes_per_file',
	'one_recipe_per_file',
	'blocks_of_files',
	'book_keywords',
	'keyword_dedup',
	'ingredient_dedup',
	'assistant',
	'recipe_enrichment',
	'recipe_ingredients',
	'recipe_ingredients_fallback',
	'recipe_semantics'
]);
export type ModelRole = z.infer<typeof modelRoleSchema>;

const providerConfigSchema = z.object({
	provider: aiProviderSchema,
	api_key_set: z.boolean(),
	display_order: z.number().int().nonnegative(),
	model_ids: z.array(z.string())
});
export type ProviderConfig = z.infer<typeof providerConfigSchema>;

const taskAssignmentSchema = z.object({
	role: modelRoleSchema,
	position: z.number().int().nonnegative(),
	provider: aiProviderSchema,
	model_id: z.string()
});
export type TaskAssignment = z.infer<typeof taskAssignmentSchema>;

// Mirrors the ConfigRead wire shape from GET/PATCH /api/config (snake_case). API
// keys are never sent over the wire — only `api_key_set` per provider. The
// recommendations map (provider → role → model) powers the recommended-pair hint
// under each task selector.
export const configSchema = z.object({
	providers: z.array(providerConfigSchema),
	task_assignments: z.array(taskAssignmentSchema),
	recommendations: z.record(z.string(), z.record(z.string(), z.string())),
	extraction_rate_limit_per_minute: z.number().int().positive()
});

export type Config = z.infer<typeof configSchema>;

// A partial update (mirrors ConfigUpdate). Only the sections present are applied,
// in order: provider rows, then the display order, then task assignments. For a
// provider's `api_key`, omitting keeps the stored key, null/empty clears it, and a
// value sets or rotates it. An empty task `entries` removes that role's assignment.
export type ProviderConfigUpdate = {
	provider: AiProvider;
	api_key?: string | null;
	display_order?: number;
	add_models?: string[];
	remove_models?: string[];
};

export type TaskAssignmentUpdate = {
	role: ModelRole;
	entries: { provider: AiProvider; model_id: string }[];
};

export type ConfigUpdate = {
	provider_configs?: ProviderConfigUpdate[];
	provider_order?: AiProvider[];
	task_assignments?: TaskAssignmentUpdate[];
	extraction_rate_limit_per_minute?: number;
};

/** Fetch and validate the current AI configuration. `fetchFn` is injectable for SSR/tests. */
export async function fetchConfig(fetchFn: typeof fetch = fetch): Promise<Config> {
	const res = await fetchFn('/api/config');
	if (!res.ok) throw new Error(`GET /api/config → ${res.status}`);
	return configSchema.parse(await res.json());
}

/** Apply a partial configuration update and return the refreshed (key-free) config. */
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

export const aiReadinessSchema = z.object({
	extraction_available: z.boolean(),
	assistant_available: z.boolean(),
	ocr_available: z.boolean()
});
export type AiReadiness = z.infer<typeof aiReadinessSchema>;

/** Whether AI work can start — key-free, available to every signed-in user. */
export async function fetchAiReadiness(fetchFn: typeof fetch = fetch): Promise<AiReadiness> {
	const res = await fetchFn('/api/ai/readiness');
	if (!res.ok) throw new Error(`GET /api/ai/readiness → ${res.status}`);
	return aiReadinessSchema.parse(await res.json());
}
