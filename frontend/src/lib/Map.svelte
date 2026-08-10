<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { Event } from '$lib/api';
	import { severityColor, worstSeverity } from '$lib/severity';

	interface Props {
		events: Event[];
		selectedId: string | null;
		onselect: (id: string) => void;
	}

	let { events, selectedId, onselect }: Props = $props();

	let container = $state<HTMLDivElement | undefined>();
	// $state, not a plain let: the marker effect below reads it, so it has to be
	// tracked for that effect to re-fire once the map finishes loading.
	let map = $state<import('leaflet').Map | undefined>();
	let mapError = $state(false);
	// The one resolved Leaflet instance, shared by both effects — see loadLeaflet().
	let leaflet: typeof import('leaflet') | undefined;
	let clusterGroup: import('leaflet').MarkerClusterGroup | undefined;
	// Plain let, deliberately not $state: guards one-shot init without making
	// the init effect re-run when it flips.
	let initStarted = false;
	// Bumped by retry() to deliberately re-run the init effect.
	let initToken = $state(0);

	const WELLINGTON_CENTER: [number, number] = [-41.2865, 174.7762];

	function severityIcon(
		L: typeof import('leaflet'),
		severity: string | null | undefined,
		selected: boolean
	) {
		const size = selected ? 22 : 16;
		const color = severityColor(severity);
		return L.divIcon({
			className: 'severity-marker',
			html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #1e293b;box-sizing:border-box;"></div>`,
			iconSize: [size, size]
		});
	}

	// Clusters are coloured by their worst-severity member, not an average —
	// a cluster of mostly-low reports with one high should still read as
	// urgent, not get diluted away.
	function clusterIcon(L: typeof import('leaflet'), cluster: import('leaflet').MarkerCluster) {
		const children = cluster.getAllChildMarkers();
		const severities = children.map((m) => (m.options as { severity?: string | null }).severity);
		const color = severityColor(worstSeverity(severities));
		const count = children.length;
		const size = 32 + Math.min(count, 20);
		return L.divIcon({
			className: 'severity-cluster',
			html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #1e293b;box-sizing:border-box;display:flex;align-items:center;justify-content:center;color:white;font-weight:600;font-size:12px;">${count}</div>`,
			iconSize: [size, size]
		});
	}

	function renderMarkers(L: typeof import('leaflet')) {
		if (!map) return;
		if (clusterGroup) {
			clusterGroup.clearLayers();
		} else {
			clusterGroup = L.markerClusterGroup({
				iconCreateFunction: (cluster) => clusterIcon(L, cluster)
			});
			map.addLayer(clusterGroup);
		}

		for (const event of events) {
			const { lat, lon } = event.location;
			if (lat == null || lon == null) continue;

			const isSelected = event.id === selectedId;
			const marker = L.marker([lat, lon], {
				icon: severityIcon(L, event.severity, isSelected)
			});
			(marker.options as { severity?: string | null }).severity = event.severity;
			marker.on('click', () => onselect(event.id));
			marker.bindTooltip(event.hazard_type ?? 'Report', { direction: 'top' });
			clusterGroup.addLayer(marker);
		}
	}

	// leaflet.markercluster does not import Leaflet at all: its UMD factory takes
	// only `exports` and reads a *bare global* `L`, which Leaflet publishes as
	// `window.L` on the very last line of its own evaluation. Because there is no
	// import edge between them, the bundler has nothing to order them by — the
	// built markercluster chunk imports only the CommonJS helper, never the
	// leaflet chunk. Loading both concurrently was therefore a race decided by
	// chunk fetch order: cold cache (markercluster is 34KB vs Leaflet's 149KB)
	// lost it and threw `L is not defined`, killing the map entirely; a warm
	// cache won it and the map rendered.
	//
	// So: await Leaflet to completion first, then load markercluster.
	//
	// `.default` matters as much as the ordering — it's the CJS exports object,
	// the same one markercluster augments (and the same object as `window.L`).
	// The interop *namespace* is a key-set snapshot taken before markercluster
	// attaches `markerClusterGroup`, so reading that property off the namespace
	// is always undefined, which is what the warm-cache path used to hit.
	async function loadLeaflet(): Promise<typeof import('leaflet')> {
		const mod = await import('leaflet');
		const L = ((mod as { default?: typeof import('leaflet') }).default ??
			mod) as typeof import('leaflet');
		await import('leaflet.markercluster');
		return L;
	}

	$effect(() => {
		initToken;
		if (!container || initStarted) return;
		initStarted = true;
		let cancelled = false;

		// Leaflet touches `window`/`document` on init — dynamic import keeps
		// this out of the prerender/SSR path entirely (see dashboard/+page.ts).
		loadLeaflet()
			.then((L) => {
				if (cancelled || !container) return;
				const m = L.map(container).setView(WELLINGTON_CENTER, 12);
				L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
					attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a>',
					maxZoom: 19
				}).addTo(m);
				// leaflet before map: the marker effect below fires the moment
				// `map` is set and reads both.
				leaflet = L;
				map = m;
			})
			.catch((err) => {
				if (cancelled) return;
				// Never fail silently — a blank panel with no explanation reads as
				// "no reports", which for an emergency-staff tool is a false
				// all-clear (same reasoning as the dashboard's connection state).
				console.error('[map] failed to initialise', err);
				mapError = true;
			});

		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		// Re-render markers whenever events or the selection change. `map` is
		// $state, so this also fires once for the initial render the moment the
		// map finishes loading — the init effect deliberately doesn't call
		// renderMarkers itself.
		events;
		selectedId;
		if (map && leaflet) {
			renderMarkers(leaflet);
		}
	});

	function retry() {
		mapError = false;
		initStarted = false;
		// Bumping this re-runs the init effect. Reassigning `container` wouldn't:
		// it's a bind:this target, and setting it away and back inside one batch
		// settles on the same value, so nothing would be seen to change.
		initToken++;
	}

	onDestroy(() => {
		map?.remove();
	});
</script>

<div class="relative h-full w-full">
	<div bind:this={container} class="h-full w-full"></div>

	{#if mapError}
		<div
			class="absolute inset-0 z-[500] flex flex-col items-center justify-center gap-2 bg-slate-50 p-4 text-center"
		>
			<p class="text-sm font-medium text-slate-800">The map didn't load.</p>
			<p class="max-w-xs text-xs text-slate-500">
				The report list beside it is still live — this panel only affects the map view.
			</p>
			<button
				class="mt-1 rounded-md border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
				onclick={retry}
			>
				Retry
			</button>
		</div>
	{/if}
</div>
