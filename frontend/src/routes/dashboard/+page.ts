// Client-only: the map (Leaflet) and the 10-15s event poll both need the
// browser. Still prerendered as a static shell (see root +layout.ts) that
// hydrates on load — no server-renderable content to lose by disabling ssr.
export const ssr = false;
