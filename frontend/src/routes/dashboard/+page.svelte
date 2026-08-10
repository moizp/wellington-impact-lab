<script lang="ts">
	import 'leaflet/dist/leaflet.css';
	import 'leaflet.markercluster/dist/MarkerCluster.css';
	import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
	import EventMap from '$lib/Map.svelte';
	import { actionLabel } from '$lib/actions';
	import { ApiUnreachableError, getEvents, type Event } from '$lib/api';
	import { severityColor } from '$lib/severity';

	const POLL_INTERVAL_MS = 12_000;

	// Backend reachability is tracked separately from `events` — a failed
	// poll must never be indistinguishable from "genuinely no reports": for
	// an emergency-staff tool, silently showing an empty feed on a network
	// blip is a false all-clear, not just a missing indicator.
	let events = $state<Event[]>([]);
	let selectedId = $state<string | null>(null);
	let connection = $state<'ok' | 'unreachable' | 'error'>('ok');
	let lastUpdated = $state<Date | null>(null);
	let severityFilter = $state<'all' | 'low' | 'medium' | 'high'>('all');

	const SEVERITY_OPTIONS: { value: typeof severityFilter; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'low', label: 'Low' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'high', label: 'High' }
	];

	// Detail panel keeps looking up the selection in the full, unfiltered
	// list — switching the filter shouldn't make an already-open report
	// disappear out from under the staff member reading it.
	const selectedEvent = $derived(events.find((e) => e.id === selectedId) ?? null);

	const filteredEvents = $derived(
		severityFilter === 'all' ? events : events.filter((e) => e.severity === severityFilter)
	);

	// Counts always reflect the full unfiltered list, not filteredEvents —
	// otherwise selecting "High" would make every other toggle's count
	// collapse to what's visible, rather than showing what's actually there.
	const severityCounts = $derived.by(() => {
		const counts: Record<'all' | 'low' | 'medium' | 'high', number> = {
			all: events.length,
			low: 0,
			medium: 0,
			high: 0
		};
		for (const event of events) {
			if (event.severity === 'low' || event.severity === 'medium' || event.severity === 'high') {
				counts[event.severity]++;
			}
		}
		return counts;
	});

	const groupedByLocation = $derived.by(() => {
		const groups = new Map<string, Event[]>();
		for (const event of filteredEvents) {
			const key = event.location.suburb ?? 'Unknown location';
			const list = groups.get(key) ?? [];
			list.push(event);
			groups.set(key, list);
		}
		return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
	});

	async function refresh() {
		try {
			// Keep showing the last-known events if this poll fails — losing
			// the feed entirely on a transient blip is worse than showing
			// slightly stale data with a clear "unreachable" indicator.
			events = await getEvents();
			connection = 'ok';
			lastUpdated = new Date();
		} catch (err) {
			connection = err instanceof ApiUnreachableError ? 'unreachable' : 'error';
		}
	}

	$effect(() => {
		refresh();
		const interval = setInterval(refresh, POLL_INTERVAL_MS);
		return () => clearInterval(interval);
	});

	function formatTime(iso: string): string {
		return new Date(iso).toLocaleTimeString('en-NZ', {
			timeZone: 'Pacific/Auckland',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatUpdatedAt(date: Date): string {
		return date.toLocaleTimeString('en-NZ', {
			timeZone: 'Pacific/Auckland',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>Staff dashboard — Wellington Emergency Information Triage</title>
</svelte:head>

<div class="flex h-screen flex-col">
	<header class="flex items-center justify-between border-b border-slate-200 px-4 py-2">
		<h1 class="text-lg font-semibold text-slate-900">Wellington hazard triage</h1>
		<div class="flex items-center gap-2 text-xs">
			{#if connection === 'ok'}
				<span class="h-2 w-2 rounded-full bg-green-500"></span>
				<span class="text-slate-500">
					Live{#if lastUpdated}&nbsp;— updated {formatUpdatedAt(lastUpdated)}{/if}
				</span>
			{:else if connection === 'unreachable'}
				<span class="h-2 w-2 animate-pulse rounded-full bg-red-500"></span>
				<span class="font-medium text-red-600">
					Can't reach the server{#if lastUpdated}&nbsp;— showing data from {formatUpdatedAt(
							lastUpdated
						)}{/if}
				</span>
			{:else}
				<span class="h-2 w-2 rounded-full bg-amber-500"></span>
				<span class="font-medium text-amber-700">Server error — retrying</span>
			{/if}
		</div>
	</header>

	<div class="grid flex-1 grid-cols-[1.2fr_1fr] overflow-hidden">
		<div class="relative border-r border-slate-200">
			<EventMap events={filteredEvents} {selectedId} onselect={(id) => (selectedId = id)} />
		</div>

		<div class="grid grid-rows-[auto_1fr_auto] overflow-hidden">
			<div class="flex items-center gap-1 border-b border-slate-200 px-3 py-2">
				<span class="mr-1 text-xs font-medium text-slate-500">Severity:</span>
				{#each SEVERITY_OPTIONS as option (option.value)}
					<button
						class="rounded-full border px-2.5 py-1 text-xs font-medium transition-colors {severityFilter ===
						option.value
							? 'border-slate-900 bg-slate-900 text-white'
							: 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'}"
						onclick={() => (severityFilter = option.value)}
					>
						{option.label} ({severityCounts[option.value]})
					</button>
				{/each}
			</div>

			<div class="overflow-y-auto p-3">
				{#each groupedByLocation as [location, locationEvents] (location)}
					<div class="mb-4">
						<h2 class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
							{location}
						</h2>
						<div class="flex flex-col gap-2">
							{#each locationEvents as event (event.id)}
								<button
									class="rounded-md border px-3 py-2 text-left transition-colors {selectedId ===
									event.id
										? 'border-slate-900 bg-slate-100'
										: 'border-slate-200 bg-white hover:bg-slate-50'}"
									onclick={() => (selectedId = event.id)}
								>
									<div class="flex items-center gap-2">
										<span
											class="h-2.5 w-2.5 rounded-full"
											style="background-color: {severityColor(event.severity)}"
										></span>
										<span class="text-sm font-medium text-slate-800">
											{event.hazard_type ?? 'Uncategorised report'}
										</span>
										<span class="ml-auto text-xs text-slate-400">
											{formatTime(event.event_time)}
										</span>
									</div>
									<p class="mt-1 line-clamp-2 text-xs text-slate-600">
										{event.clarified_text ?? event.raw_text}
									</p>
								</button>
							{/each}
						</div>
					</div>
				{:else}
					{#if connection !== 'ok'}
						<p class="p-2 text-sm text-red-600">
							Couldn't load reports — see the connection status above.
						</p>
					{:else if events.length > 0}
						<p class="p-2 text-sm text-slate-500">No reports match this filter.</p>
					{:else}
						<p class="p-2 text-sm text-slate-500">No reports yet.</p>
					{/if}
				{/each}
			</div>

			<div class="max-h-[45vh] overflow-y-auto border-t border-slate-200 p-4">
				{#if selectedEvent}
					<div class="flex flex-col gap-3">
						<div>
							<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
								Report
							</p>
							<p class="mt-1 text-sm text-slate-800">{selectedEvent.raw_text}</p>
						</div>

						{#if selectedEvent.clarification_question}
							<div>
								<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
									Follow-up
								</p>
								<p class="mt-1 text-sm text-slate-800">
									<span class="text-slate-500">Q:</span> {selectedEvent.clarification_question}
								</p>
								{#if selectedEvent.clarification_answer}
									<p class="mt-1 text-sm text-slate-800">
										<span class="text-slate-500">A:</span> {selectedEvent.clarification_answer}
									</p>
								{/if}
							</div>
						{/if}

						{#if selectedEvent.actions && selectedEvent.actions.length > 0}
							<div>
								<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
									Suggested actions
								</p>
								<ul class="mt-1 list-disc pl-5 text-sm text-slate-800">
									{#each selectedEvent.actions as action (action)}
										<li>{actionLabel(action)}</li>
									{/each}
								</ul>
							</div>
						{/if}

						{#if selectedEvent.severity}
							<div>
								<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
									Severity
								</p>
								<p
									class="mt-1 inline-block rounded px-2 py-0.5 text-sm font-medium text-white"
									style="background-color: {severityColor(selectedEvent.severity)}"
									title={selectedEvent.rationale ?? ''}
								>
									{selectedEvent.severity}
								</p>
								{#if selectedEvent.rationale}
									<p class="mt-1 text-xs text-slate-500">{selectedEvent.rationale}</p>
								{/if}
							</div>
						{/if}

						{#if selectedEvent.official_context && selectedEvent.official_context.length > 0}
							<div>
								<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
									Official context
								</p>
								<ul class="mt-1 flex flex-col gap-1">
									{#each selectedEvent.official_context as item (item.summary)}
										<li class="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700">
											<span class="font-medium">{item.source}</span> — {item.summary}
											<span class="text-slate-400">({item.minutes_ago}m ago)</span>
										</li>
									{/each}
								</ul>
							</div>
						{/if}
					</div>
				{:else}
					<p class="text-sm text-slate-500">Select a report to see details.</p>
				{/if}
			</div>
		</div>
	</div>
</div>
