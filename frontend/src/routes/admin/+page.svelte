<script lang="ts">
	import { onMount } from 'svelte';
	import AdminTabs, { type AdminTab } from '$lib/components/AdminTabs.svelte';
	import ConfigSettings, {
		type ConfigSettingsConfig
	} from '$lib/components/ConfigSettings.svelte';
	import { fetchConfig, updateConfig, type Config, type ConfigUpdate } from '$lib/api/config';
	import { pageTitle } from '$lib/title';

	// One tab today (Settings); the extraction reports (MY-11) slot in here as a second tab.
	const tabs: AdminTab[] = [{ id: 'settings', label: 'Settings' }];
	let active = $state('settings');

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let config = $state<Config | null>(null);

	// Map the snake_case wire shape to the component's camelCase props.
	let settingsConfig = $derived<ConfigSettingsConfig | null>(
		config
			? {
					aiProvider: config.ai_provider,
					apiKeySet: config.api_key_set,
					rateLimit: config.extraction_rate_limit_per_minute,
					providers: config.providers.map((p) => ({
						name: p.name,
						requiresApiKey: p.requires_api_key
					}))
				}
			: null
	);

	async function load() {
		status = 'loading';
		try {
			config = await fetchConfig();
			status = 'ready';
		} catch (err) {
			console.error('failed to load config', err);
			status = 'error';
		}
	}

	// The PATCH returns the refreshed (key-free) config; assigning it re-seeds the form.
	async function save(patch: ConfigUpdate) {
		config = await updateConfig(patch);
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle('Admin')}</title>
</svelte:head>

<section class="admin">
	<header class="head">
		<p class="label">Operations</p>
		<h1>Admin</h1>
	</header>

	<AdminTabs {tabs} {active} onSelect={(id) => (active = id)} />

	{#if status === 'ready' && settingsConfig}
		{#if active === 'settings'}
			<ConfigSettings config={settingsConfig} onSave={save} />
		{/if}
	{:else if status === 'loading'}
		<p class="msg">Loading settings…</p>
	{:else}
		<p class="msg">Couldn’t load settings.</p>
		<button class="retry" onclick={load}>Try again</button>
	{/if}
</section>

<style>
	.admin {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 3.5rem var(--page-h) 5rem;
	}
	.head {
		margin-bottom: 2.5rem;
	}
	.head h1 {
		font-family: var(--f-serif);
		font-weight: 600;
		font-size: 2.4rem;
		letter-spacing: -0.01em;
		margin: 0.3rem 0 0;
	}
	.msg {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.3rem;
		color: var(--muted);
		margin: 0;
	}
	.retry {
		margin-top: 1rem;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.85rem;
		background: var(--ink);
		color: var(--bg);
		border: none;
		border-radius: 3px;
		padding: 0.55rem 1.1rem;
		cursor: pointer;
	}
	.retry:hover {
		background: var(--clay-deep);
	}
</style>
