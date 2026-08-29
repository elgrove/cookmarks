import { z } from 'zod';

// Mirrors AuthMe from GET /api/auth/me — the signed-in user plus the deployment's
// auth mode ("session" | "none"); "none" means the backend runs with no accounts and
// the SPA hides all login chrome.
export const authMeSchema = z.object({
	id: z.string(),
	username: z.string(),
	is_admin: z.boolean(),
	auth_mode: z.string(),
	cooking_instructions: z.string().nullable().optional()
});

export const userSchema = z.object({
	id: z.string(),
	username: z.string(),
	is_admin: z.boolean(),
	created_at: z.string()
});

export type AuthMe = z.infer<typeof authMeSchema>;
export type User = z.infer<typeof userSchema>;

export async function fetchMe(fetchFn: typeof fetch = fetch): Promise<AuthMe | null> {
	const res = await fetchFn('/api/auth/me');
	if (res.status === 401) return null;
	if (!res.ok) throw new Error(`GET /api/auth/me → ${res.status}`);
	return authMeSchema.parse(await res.json());
}

export async function updateMe(
	input: { cooking_instructions?: string | null },
	fetchFn: typeof fetch = fetch
): Promise<AuthMe> {
	const res = await fetchFn('/api/auth/me', {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(input)
	});
	if (!res.ok) throw new Error(await errorMessage(res, "Couldn't update your instructions."));
	return authMeSchema.parse(await res.json());
}

/** Sign in. Rejects with the backend's generic message on bad credentials. */
export async function login(
	username: string,
	password: string,
	fetchFn: typeof fetch = fetch
): Promise<AuthMe> {
	const res = await fetchFn('/api/auth/login', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ username, password })
	});
	if (!res.ok) throw new Error(await errorMessage(res, 'Incorrect username or password.'));
	return authMeSchema.parse(await res.json());
}

export async function logout(fetchFn: typeof fetch = fetch): Promise<void> {
	const res = await fetchFn('/api/auth/logout', { method: 'POST' });
	if (!res.ok) throw new Error(`POST /api/auth/logout → ${res.status}`);
}

export async function fetchUsers(fetchFn: typeof fetch = fetch): Promise<User[]> {
	const res = await fetchFn('/api/users');
	if (!res.ok) throw new Error(`GET /api/users → ${res.status}`);
	return z.array(userSchema).parse(await res.json());
}

export async function createUser(
	input: { username: string; password: string; is_admin: boolean },
	fetchFn: typeof fetch = fetch
): Promise<User> {
	const res = await fetchFn('/api/users', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(input)
	});
	if (!res.ok) throw new Error(await errorMessage(res, "Couldn't create that account."));
	return userSchema.parse(await res.json());
}

export async function deleteUser(id: string, fetchFn: typeof fetch = fetch): Promise<void> {
	const res = await fetchFn(`/api/users/${id}`, { method: 'DELETE' });
	if (!res.ok) throw new Error(await errorMessage(res, "Couldn't delete that account."));
}

export async function resetPassword(
	id: string,
	password: string,
	fetchFn: typeof fetch = fetch
): Promise<void> {
	const res = await fetchFn(`/api/users/${id}/password`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ password })
	});
	if (!res.ok) throw new Error(await errorMessage(res, "Couldn't reset that password."));
}

/** The backend's `detail` when it sends one — these are user-facing messages
 *  (a taken username, the last admin), so surfacing them beats a status code. */
async function errorMessage(res: Response, fallback: string): Promise<string> {
	try {
		const body = (await res.json()) as { detail?: unknown };
		if (typeof body.detail === 'string' && body.detail) return body.detail;
	} catch {
		/* no JSON body — fall through */
	}
	return fallback;
}
