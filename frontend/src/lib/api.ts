// Direct fetch() to the full backend URL, baked in at build time — no
// rewrite-proxy needed since CORS is already open on the backend (see
// docs/FRONTEND_PLAN.md "Hosting: dual-platform design").
const API_URL = import.meta.env.VITE_API_URL as string;

export interface CommunityReport {
	raw_text: string;
	suburb?: string | null;
	lat?: number | null;
	lon?: number | null;
}

export interface Location {
	suburb?: string | null;
	lat?: number | null;
	lon?: number | null;
}

export interface OfficialContextItem {
	source: string;
	hazard_type: string;
	severity_hint: 'low' | 'medium' | 'high';
	distance_km?: number | null;
	minutes_ago: number;
	summary: string;
}

export interface Event {
	id: string;
	ingested_at: string;
	event_time: string;
	location: Location;
	raw_text: string;
	clarified_text?: string | null;
	clarification_question?: string | null;
	clarification_answer?: string | null;
	actions?: string[] | null;
	contact?: string | null;
	official_context?: OfficialContextItem[];
	related_report_id?: string | null;
	hazard_type?: string | null;
	severity?: string | null;
	rationale?: string | null;
	status: 'awaiting_clarification' | 'new' | 'triaged';
}

export interface GetEventsParams {
	suburb?: string;
	hazard_type?: string;
	source_type?: string;
}

// Thrown when the backend itself couldn't be reached at all (DNS failure,
// connection refused, CORS block, offline) — distinct from the backend
// responding with an error status. UI code uses this to show "can't reach
// the server" rather than a generic/misleading failure message.
export class ApiUnreachableError extends Error {
	constructor() {
		super("Can't reach the server. Check your connection and try again.");
		this.name = 'ApiUnreachableError';
	}
}

async function doFetch(path: string, init?: RequestInit): Promise<Response> {
	let res: Response;
	try {
		res = await fetch(`${API_URL}${path}`, init);
	} catch {
		throw new ApiUnreachableError();
	}
	if (!res.ok) {
		throw new Error(`${path} failed: ${res.status} ${await res.text()}`);
	}
	return res;
}

export async function getEvents(params: GetEventsParams = {}): Promise<Event[]> {
	const query = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value) query.set(key, value);
	}
	const qs = query.toString();
	const res = await doFetch(`/events${qs ? `?${qs}` : ''}`);
	return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
	const res = await doFetch(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	return res.json();
}

export function submitCommunityReport(report: CommunityReport): Promise<Event> {
	return postJson<Event>('/events/community-report', report);
}

// Phase 2, step 1 (Clarifier Call 1 — "ask"). Returns the event with
// clarification_question set; does not trigger triage yet.
export function submitForClarification(report: CommunityReport): Promise<Event> {
	return postJson<Event>('/events/community-report/clarify', report);
}

export interface ClarificationAnswer {
	answer: string;
	contact?: string | null;
}

// Phase 2, step 2 (Clarifier Call 2 — "act"). Returns the event with actions
// set, and triggers async triage on the backend.
export function submitClarificationAnswer(
	eventId: string,
	body: ClarificationAnswer
): Promise<Event> {
	return postJson<Event>(`/events/${eventId}/clarification-answer`, body);
}

// User-facing error text — ApiUnreachableError's message is already
// friendly; anything else (a non-2xx response) gets a generic message
// rather than surfacing the technical "path failed: 500 ..." detail.
export function describeError(err: unknown): string {
	if (err instanceof ApiUnreachableError) return err.message;
	return 'The server had trouble processing that. Please try again.';
}
