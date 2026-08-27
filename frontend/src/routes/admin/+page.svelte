<script lang="ts">
	import { onMount } from 'svelte';
	import AdminTabs, { type AdminTab } from '$lib/components/AdminTabs.svelte';
	import ConfigSettings, {
		type ConfigSettingsConfig
	} from '$lib/components/ConfigSettings.svelte';
	import TasksPanel from '$lib/components/TasksPanel.svelte';
	import TaskRunsPanel from '$lib/components/TaskRunsPanel.svelte';
	import UsersPanel from '$lib/components/UsersPanel.svelte';
	import { fetchConfig, updateConfig, type Config, type ConfigUpdate } from '$lib/api/config';
	import { triggerBookKeywords, triggerDedupKeywords, triggerCalibreSync } from '$lib/api/tasks';
	import { fetchTaskRuns, type TaskRun } from '$lib/api/task-runs';
	import {
		createUser,
		deleteUser,
		fetchUsers,
		resetPassword,
		type User
	} from '$lib/api/auth';
	import { currentUser } from '$lib/auth';
	import { pageTitle } from '$lib/title';

	const tabs: AdminTab[] = [
		{ id: 'settings', label: 'Settings' },
		{ id: 'tasks', label: 'Tasks' },
		{ id: 'task-runs', label: 'Task Runs' },
		{ id: 'users', label: 'Users' }
	];
	let active = $state('settings');

	let status = $state<'loading' | 'error' | 'ready'>('loading');
	let config = $state<Config | null>(null);

	// Task-run history loads lazily the first time its tab is opened, with its own state
	// so a settings failure (or never opening this tab) never touches it.
	let runsStatus = $state<'idle' | 'loading' | 'error' | 'ready'>('idle');
	let runs = $state<TaskRun[]>([]);

	// Map the snake_case wire shape to the component's camelCase props.
	let settingsConfig = $derived<ConfigSettingsConfig | null>(
		config
			? {
					extractionProvider: config.ai_provider,
					extractionApiKeySet: config.api_key_set,
					assistantProvider: config.assistant_provider,
					assistantApiKeySet: config.assistant_api_key_set,
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
			runs = await fetchTaskRuns();
			runsStatus = 'ready';
		} catch (err) {
			console.error('failed to load task runs', err);
			runsStatus = 'error';
		}
	}

	// Accounts load lazily on first open, the same shape as the task-run history.
	let usersStatus = $state<'idle' | 'loading' | 'error' | 'ready'>('idle');
	let users = $state<User[]>([]);

	async function loadUsers() {
		usersStatus = 'loading';
		try {
			users = await fetchUsers();
			usersStatus = 'ready';
		} catch (err) {
			console.error('failed to load users', err);
			usersStatus = 'error';
		}
	}

	function selectTab(id: string) {
		active = id;
		if (id === 'task-runs' && runsStatus === 'idle') loadRuns();
		if (id === 'users' && usersStatus === 'idle') loadUsers();
	}

	onMount(load);
</script>

<svelte:head>
	<title>{pageTitle('Admin')}</title>
</svelte:head>

<section class="admin">
	<header class="head">
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
		<TasksPanel
			onRun={({ regenerate }) => triggerBookKeywords(regenerate)}
			onDedup={() => triggerDedupKeywords()}
			onSync={() => triggerCalibreSync()}
		/>
	{:else if active === 'task-runs'}
		{#if runsStatus === 'ready'}
			<TaskRunsPanel {runs} />
		{:else if runsStatus === 'error'}
			<p class="msg">Couldn’t load task-run history.</p>
			<button class="retry" onclick={loadRuns}>Try again</button>
		{:else}
			<p class="msg">Loading task-run history…</p>
		{/if}
	{:else if active === 'users'}
		{#if usersStatus === 'ready'}
			<UsersPanel
				{users}
				currentUserId={$currentUser?.id}
				onCreate={async (input) => {
					await createUser(input);
					await loadUsers();
				}}
				onDelete={async (id) => {
					await deleteUser(id);
					await loadUsers();
				}}
				onResetPassword={(id, password) => resetPassword(id, password)}
			/>
		{:else if usersStatus === 'error'}
			<p class="msg">Couldn’t load accounts.</p>
			<button class="retry" onclick={loadUsers}>Try again</button>
		{:else}
			<p class="msg">Loading accounts…</p>
		{/if}
	{/if}
</section>

<style>
	.admin {
		max-width: var(--max-w);
		margin: 0 auto;
		padding: var(--page-pt) var(--page-h) 5rem;
	}
	.head {
		margin-bottom: 2.5rem;
	}
	.head h1 {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0.2rem 0 0;
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
