export const SEVERITY_COLORS: Record<string, string> = {
	low: '#16a34a',
	medium: '#d97706',
	high: '#dc2626'
};

export function severityColor(severity: string | null | undefined): string {
	return (severity && SEVERITY_COLORS[severity]) || '#94a3b8';
}

// high > medium > low > untriaged — a cluster of pins should read as
// dangerous as its worst member, not an average or whatever's on top.
const SEVERITY_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

export function worstSeverity(severities: (string | null | undefined)[]): string | null {
	let worst: string | null = null;
	let worstRank = -1;
	for (const s of severities) {
		const rank = (s && SEVERITY_RANK[s]) || 0;
		if (rank > worstRank) {
			worstRank = rank;
			worst = s ?? null;
		}
	}
	return worst;
}
