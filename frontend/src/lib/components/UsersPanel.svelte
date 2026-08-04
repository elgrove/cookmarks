<script module lang="ts">
	import type { User } from '$lib/api/auth';

	export type UsersPanelProps = {
		/** Every account, oldest first. Network-free and verifiable in isolation;
		 *  the admin route owns the fetching. */
		users: User[];
		/** The signed-in account's id — its own row can't be deleted. */
		currentUserId?: string;
		onCreate?: (input: {
			username: string;
			password: string;
			is_admin: boolean;
		}) => Promise<void> | void;
		onDelete?: (id: string) => Promise<void> | void;
		onResetPassword?: (id: string, password: string) => Promise<void> | void;
	};

	const dateFmt = new Intl.DateTimeFormat('en-GB', {
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});

	function created(iso: string): string {
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? '—' : dateFmt.format(d);
	}
</script>

<script lang="ts">
	let { users, currentUserId, onCreate, onDelete, onResetPassword }: UsersPanelProps = $props();

	let username = $state('');
	let password = $state('');
	let isAdmin = $state(false);
	let busy = $state(false);
	let error = $state('');

	// Which row's password is being reset, and to what.
	let resettingId = $state<string | null>(null);
	let newPassword = $state('');

	let adminCount = $derived(users.filter((u) => u.is_admin).length);
	let canCreate = $derived(username.trim().length > 0 && password.length > 0 && !busy);

	// The last admin can't be removed, nor can you remove yourself — the backend
	// enforces both; disabling here explains why before the click.
	function deleteBlockedReason(user: User): string {
		if (user.id === currentUserId) return 'You cannot delete your own account';
		if (user.is_admin && adminCount <= 1) return 'The last admin cannot be deleted';
		return '';
	}

	async function run(action: () => Promise<void> | void) {
		busy = true;
		error = '';
		try {
			await action();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong.';
		} finally {
			busy = false;
		}
	}

	async function create() {
		if (!canCreate) return;
		const input = { username: username.trim(), password, is_admin: isAdmin };
		await run(async () => {
			await onCreate?.(input);
			username = '';
			password = '';
			isAdmin = false;
		});
	}

	async function resetPassword(id: string) {
		if (!newPassword) return;
		const value = newPassword;
		await run(async () => {
			await onResetPassword?.(id, value);
			resettingId = null;
			newPassword = '';
		});
	}
</script>

<section
	class="panel"
	data-verify-unit="users-panel"
	data-verify-user-count={users.length}
	data-verify-admin-count={adminCount}
	data-verify-error={error}
	data-verify-busy={String(busy)}
>
	{#if users.length === 0}
		<p class="empty">No accounts yet.</p>
	{:else}
		<table class="users">
			<caption class="sr-only">Accounts on this Cookmarks deployment</caption>
			<thead>
				<tr>
					<th scope="col">Username</th>
					<th scope="col">Role</th>
					<th scope="col">Added</th>
					<th scope="col"><span class="sr-only">Actions</span></th>
				</tr>
			</thead>
			<tbody>
				{#each users as user (user.id)}
					<tr data-user-id={user.id}>
						<td class="name">{user.username}</td>
						<td class="mono role">{user.is_admin ? 'Admin' : 'Member'}</td>
						<td class="mono when">{created(user.created_at)}</td>
						<td class="actions">
							{#if resettingId === user.id}
								<label class="sr-only" for={`pw-${user.id}`}>
									New password for {user.username}
								</label>
								<input
									id={`pw-${user.id}`}
									class="pw"
									type="password"
									autocomplete="new-password"
									placeholder="New password"
									bind:value={newPassword}
								/>
								<button
									class="link save-pw"
									type="button"
									disabled={busy || !newPassword}
									onclick={() => resetPassword(user.id)}
								>
									Save
								</button>
								<button
									class="link"
									type="button"
									onclick={() => {
										resettingId = null;
										newPassword = '';
									}}
								>
									Cancel
								</button>
							{:else}
								<button
									class="link reset"
									type="button"
									onclick={() => {
										resettingId = user.id;
										newPassword = '';
									}}
								>
									Reset password
								</button>
								<button
									class="link delete"
									type="button"
									disabled={busy || deleteBlockedReason(user) !== ''}
									title={deleteBlockedReason(user) || undefined}
									aria-label={deleteBlockedReason(user)
										? `Delete ${user.username} — ${deleteBlockedReason(user)}`
										: `Delete ${user.username}`}
									onclick={() => run(async () => await onDelete?.(user.id))}
								>
									Delete
								</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}

	<form
		class="create"
		onsubmit={(e) => {
			e.preventDefault();
			create();
		}}
	>
		<p class="mono heading">Add an account</p>
		<div class="row">
			<label class="label" for="new-username">Username</label>
			<input
				id="new-username"
				type="text"
				autocapitalize="none"
				spellcheck="false"
				bind:value={username}
			/>
		</div>
		<div class="row">
			<label class="label" for="new-password">Password</label>
			<input id="new-password" type="password" autocomplete="new-password" bind:value={password} />
		</div>
		<div class="row">
			<label class="label" for="new-admin">Admin</label>
			<input id="new-admin" type="checkbox" bind:checked={isAdmin} />
		</div>
		<button class="submit" type="submit" disabled={!canCreate}>Create account</button>
	</form>
</section>

<style>
	.panel {
		min-width: 0;
	}
	.empty {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1.2rem;
		color: var(--muted);
		margin: 0;
	}
	.users {
		width: 100%;
		border-collapse: collapse;
	}
	.users th {
		font-family: var(--f-mono);
		font-size: 0.68rem;
		font-weight: 400;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
		text-align: left;
		padding: 0 0 0.6rem;
		border-bottom: var(--border);
	}
	.users td {
		padding: 0.85rem 0.6rem 0.85rem 0;
		border-bottom: var(--border);
		vertical-align: middle;
	}
	.name {
		font-family: var(--f-serif);
		font-size: 1.05rem;
	}
	.role,
	.when {
		font-size: 0.78rem;
		color: var(--muted);
		white-space: nowrap;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: flex-end;
		gap: 0.5rem 0.9rem;
		border-bottom: var(--border);
	}
	.link {
		font-family: var(--f-grotesk);
		font-size: 0.8rem;
		color: var(--clay-deep);
		background: none;
		border: none;
		padding: 0;
		text-decoration: underline;
		text-underline-offset: 2px;
		cursor: pointer;
	}
	.link:hover:not(:disabled) {
		color: var(--ink);
	}
	.link:disabled {
		color: var(--muted);
		cursor: not-allowed;
		text-decoration-style: dotted;
	}
	.error {
		font-family: var(--f-serif);
		font-style: italic;
		color: var(--clay-deep);
		margin: 1rem 0 0;
	}
	.create {
		margin-top: 2.5rem;
		max-width: 26rem;
	}
	.heading {
		font-size: 0.68rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0 0 0.4rem;
	}
	.row {
		display: grid;
		grid-template-columns: 8rem 1fr;
		align-items: center;
		gap: 1rem;
		padding: 0.8rem 0;
		border-bottom: var(--border);
	}
	.label {
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		color: var(--muted);
	}
	input[type='text'],
	input[type='password'] {
		font-family: var(--f-grotesk);
		font-size: 0.9rem;
		color: var(--ink);
		background: var(--bg);
		border: var(--border-strong);
		border-radius: 3px;
		padding: 0.5rem 0.65rem;
	}
	input[type='checkbox'] {
		justify-self: start;
		accent-color: var(--clay);
	}
	.pw {
		max-width: 11rem;
	}
	.submit {
		margin-top: 1.6rem;
		font-family: var(--f-grotesk);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--bg);
		background: var(--ink);
		border: 1px solid var(--ink);
		border-radius: 3px;
		padding: 0.6rem 1.4rem;
		cursor: pointer;
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
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
		border: 0;
	}
	@media (max-width: 760px) {
		/* Drop the "Added" column whole — header and cells — rather than leaving a
		   header over nothing. */
		.users th:nth-child(3),
		.users td.when {
			display: none;
		}
		.row {
			grid-template-columns: 1fr;
			gap: 0.4rem;
		}
	}
</style>
