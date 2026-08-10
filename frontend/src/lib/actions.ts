// Human-readable text for each value in app.clarifier.ACTION_VOCABULARY —
// shared between the report form (Phase 2 result) and the staff dashboard
// (detail panel) so both ever show one label per action, not two.
export const ACTION_LABELS: Record<string, string> = {
	check_neighbours: 'Check in with your neighbours',
	monitor_situation: 'Keep an eye on the situation',
	document_further: 'Take photos or notes if it changes',
	call_111: 'If this becomes life-threatening, call 111',
	evacuate: 'Consider moving to a safer location',
	none: 'No further action needed right now'
};

export function actionLabel(action: string): string {
	return ACTION_LABELS[action] ?? action;
}
