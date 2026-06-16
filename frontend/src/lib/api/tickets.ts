import { z } from 'zod';

// Mirrors TicketResult from POST /api/tickets — the filed Linear issue's human
// identifier (e.g. "MY-42") and its url.
export const ticketResultSchema = z.object({
	identifier: z.string(),
	url: z.string()
});

export type TicketResult = z.infer<typeof ticketResultSchema>;

// Mirrors TicketCreate (snake_case on the wire). `page_url` records where the user
// was when they filed it.
export type TicketInput = {
	title: string;
	description: string;
	page_url: string | null;
};

/** Whether the in-app ticket form is offered — true only when the backend's Linear
 *  integration is configured. `fetchFn` is injectable for SSR/tests. */
export async function fetchTicketsEnabled(fetchFn: typeof fetch = fetch): Promise<boolean> {
	const res = await fetchFn('/api/tickets/enabled');
	if (!res.ok) throw new Error(`GET /api/tickets/enabled → ${res.status}`);
	const body = (await res.json()) as { enabled?: unknown };
	return body.enabled === true;
}

/** File a ticket, opening an issue in the Cookmarks Linear project. Rejects if the
 *  backend couldn't file it (e.g. Linear unreachable). `fetchFn` is injectable. */
export async function submitTicket(
	input: TicketInput,
	fetchFn: typeof fetch = fetch
): Promise<TicketResult> {
	const res = await fetchFn('/api/tickets', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(input)
	});
	if (!res.ok) throw new Error(`POST /api/tickets → ${res.status}`);
	return ticketResultSchema.parse(await res.json());
}
