<script lang="ts">
	import { onMount } from 'svelte';
	import AdminTabs, { type AdminTab } from '$lib/components/AdminTabs.svelte';
	import ConfigSettings, {
		type ConfigSettingsConfig
	} from '$lib/components/ConfigSettings.svelte';
	import TasksPanel from '$lib/components/TasksPanel.svelte';
	import ExtractionsPanel from '$lib/components/ExtractionsPanel.svelte';
	import { fetchConfig, updateConfig, type Config, type ConfigUpdate } from '$lib/api/config';
	import { triggerBookKeywords } from '$lib/api/tasks';
	import { fetchExtractionRuns, type ExtractionRun } from '$lib/api/extraction';
	import { pageTitle } from '$lib/title';

	const tabs: AdminTab[] = [
		{ id: 'settings', label: 'Settings' },
		{ id: 'tasks', label: 'Tasks' },
		{ id: 'extractions', label: 'Extractions' }
	];
	let active = $state('settings');

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let config = $state<Config | null>(null);

	// Extraction history loads lazily the first time its tab is opened, with its own state
	// so a settings failure (or never opening this tab) never touches it.
	let runsStatus = $state<'idle' | 'loading' | 'error' | 'ready'>('idle');
	let runs = $state<ExtractionRun[]>([]);

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

	async function loadRuns() {
		runsStatus = 'loading';
		try {
			runs = await fetchExtractionRuns();
			runsStatus = 'ready';
		} catch (err) {
			console.error('failed to load extraction runs', err);
			runsStatus = 'error';
		}
	}

	function selectTab(id: string) {
		active = id;
		if (id === 'extractions' && runsStatus === 'idle') loadRuns();
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

	<AdminTabs {tabs} {active} onSelect={selectTab} />

	{#if active === 'settings'}
		{#if status === 'ready' && settingsConfig}
			<ConfigSettings config={settingsConfig} onSave={save} />
		{:else if status === 'loading'}
			<p class="msg">Loading settings…</p>
		{:else}
			<p class="msg">Couldn’t load settings.</p>
			<button class="retry" onclick={load}>Try again</button>
		{/if}
	{:else if active === 'tasks'}
		<TasksPanel onRun={({ regenerate }) => triggerBookKeywords(regenerate)} />
	{:else if active === 'extractions'}
		{#if runsStatus === 'ready'}
			<ExtractionsPanel {runs} />
		{:else if runsStatus === 'error'}
			<p class="msg">Couldn’t load extraction history.</p>
			<button class="retry" onclick={loadRuns}>Try again</button>
		{:else}
			<p class="msg">Loading extraction history…</p>
		{/if}
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
