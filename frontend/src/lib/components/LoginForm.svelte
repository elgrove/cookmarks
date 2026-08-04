<script module lang="ts">
	export type LoginFormProps = {
		/** Injected by the route (wired to POST /api/auth/login); awaited to drive
		 *  submitting → (navigation), or → error if it rejects. Kept network-free
		 *  for isolation in the verify harness. */
		onSubmit?: (credentials: { username: string; password: string }) => Promise<void> | void;
	};

	type State = 'idle' | 'submitting' | 'error';
</script>

<script lang="ts">
	let { onSubmit }: LoginFormProps = $props();

	let username = $state('');
	let password = $state('');
	let formState = $state<State>('idle');
	let error = $state('');

	let complete = $derived(username.trim().length > 0 && password.length > 0);

	async function submit() {
		// An empty field never reaches the backend — nothing to authenticate.
		if (formState === 'submitting' || !complete) return;
		formState = 'submitting';
		error = '';
		try {
			await onSubmit?.({ username: username.trim(), password });
			// On success the route navigates away; leave the form in its submitting state
			// rather than flashing an idle form behind the transition.
		} catch (err) {
			error = err instanceof Error ? err.message : 'Incorrect username or password.';
			formState = 'error';
		}
	}
</script>

<form
	class="login"
	data-verify-unit="login-form"
	data-verify-state={formState}
	data-verify-error={error}
	onsubmit={(e) => {
		e.preventDefault();
		submit();
	}}
>
	<p class="eyebrow">Cookmarks</p>
	<h1>Sign in</h1>

	<div class="field">
		<label class="label" for="login-username">Username</label>
		<input
			id="login-username"
			name="username"
			type="text"
			autocomplete="username"
			autocapitalize="none"
			spellcheck="false"
			bind:value={username}
		/>
	</div>

	<div class="field">
		<label class="label" for="login-password">Password</label>
		<input
			id="login-password"
			name="password"
			type="password"
			autocomplete="current-password"
			bind:value={password}
		/>
	</div>

	{#if formState === 'error'}
		<p class="error" role="alert">{error}</p>
	{/if}

	<button
		class="submit"
		type="submit"
		aria-busy={formState === 'submitting'}
		disabled={formState === 'submitting' || !complete}
	>
		{formState === 'submitting' ? 'Signing in…' : 'Sign in'}
	</button>
</form>

<style>
	.login {
		display: flex;
		flex-direction: column;
		max-width: 24rem;
	}
	.eyebrow {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--clay-deep);
		margin: 0 0 0.6rem;
	}
	h1 {
		font-family: var(--f-serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(2.2rem, 5vw, 3rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin: 0 0 2rem;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		padding: 0.9rem 0;
		border-bottom: var(--border);
	}
	.label {
		font-family: var(--f-mono);
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}
	input {
		font-family: var(--f-grotesk);
		font-size: 0.95rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 3px;
		padding: 0.55rem 0.7rem;
	}
	.error {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1rem;
		color: var(--clay-deep);
		margin: 1rem 0 0;
	}
	.submit {
		margin-top: 2rem;
		align-self: flex-start;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--bg);
		background: var(--ink);
		border: 1px solid var(--ink);
		border-radius: 3px;
		padding: 0.6rem 1.6rem;
		cursor: pointer;
		transition: background 0.18s var(--ease-out);
	}
	.submit:hover:not(:disabled) {
		background: var(--ink-deep);
	}
	.submit:disabled {
		cursor: default;
		color: var(--muted);
		background: transparent;
		border-color: var(--line-strong);
	}
</style>
