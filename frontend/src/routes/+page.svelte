<script lang="ts">
	import { page } from '$app/state';
	import { actionLabel } from '$lib/actions';
	import {
		describeError,
		submitClarificationAnswer,
		submitCommunityReport,
		submitForClarification,
		type Event
	} from '$lib/api';

	const clarifierEnabled = $derived(page.url.searchParams.get('clarify') === '1');

	let rawText = $state('');
	let suburb = $state('');
	let lat = $state<number | null>(null);
	let lon = $state<number | null>(null);
	let locationStatus = $state<'pending' | 'granted' | 'denied' | 'unsupported'>('pending');

	let step = $state<'form' | 'question' | 'done'>('form');
	let currentEvent = $state<Event | null>(null);
	let answer = $state('');
	let contact = $state('');
	let resultActions = $state<string[]>([]);

	let submitting = $state(false);
	let errorMessage = $state<string | null>(null);

	$effect(() => {
		if (!navigator.geolocation) {
			locationStatus = 'unsupported';
			return;
		}
		navigator.geolocation.getCurrentPosition(
			(position) => {
				lat = position.coords.latitude;
				lon = position.coords.longitude;
				locationStatus = 'granted';
			},
			() => {
				locationStatus = 'denied';
			},
			{ timeout: 8000 }
		);
	});

	function resetForm() {
		step = 'form';
		currentEvent = null;
		rawText = '';
		suburb = '';
		answer = '';
		contact = '';
		resultActions = [];
	}

	async function handleReportSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!rawText.trim()) return;

		submitting = true;
		errorMessage = null;
		try {
			const report = { raw_text: rawText.trim(), suburb: suburb.trim() || null, lat, lon };
			if (clarifierEnabled) {
				currentEvent = await submitForClarification(report);
				step = 'question';
			} else {
				await submitCommunityReport(report);
				step = 'done';
			}
		} catch (err) {
			errorMessage = describeError(err);
		} finally {
			submitting = false;
		}
	}

	async function handleAnswerSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (!currentEvent || !answer.trim()) return;

		submitting = true;
		errorMessage = null;
		try {
			const result = await submitClarificationAnswer(currentEvent.id, {
				answer: answer.trim(),
				contact: contact.trim() || null
			});
			resultActions = result.actions ?? [];
			step = 'done';
		} catch (err) {
			errorMessage = describeError(err);
		} finally {
			submitting = false;
		}
	}

</script>

<svelte:head>
	<title>Report a hazard — Wellington Emergency Information Triage</title>
</svelte:head>

<div class="bg-teal-800 px-4 py-2 text-teal-50">
	<div class="mx-auto flex max-w-lg items-center justify-between">
		<span class="text-sm font-medium tracking-wide">Wellington City Council</span>
		<span class="text-xs text-teal-200">Pōneke | Wellington</span>
	</div>
</div>

<main class="mx-auto flex min-h-screen max-w-lg flex-col gap-6 px-4 py-10">
	<header>
		<h1 class="text-2xl font-semibold text-slate-900">Report a hazard</h1>
		<p class="mt-1 text-sm text-slate-600">
			Tell Wellington City Council what you're seeing. This helps staff prioritise their response
			— it does not replace emergency services.
		</p>
	</header>

	<div class="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
		These are hazard-planning reports, not live emergency information. In an emergency, call
		<strong>111</strong>.
	</div>

	{#if step === 'done'}
		<div class="rounded-md border border-green-300 bg-green-50 px-4 py-4 text-green-900">
			<p class="font-medium">Thanks — we've got it.</p>
			<p class="mt-1 text-sm">Your report has been sent to the council's triage system.</p>
		</div>
		{#if resultActions.length > 0}
			<div class="rounded-md border border-slate-300 bg-white px-4 py-4">
				<p class="text-sm font-medium text-slate-800">In the meantime:</p>
				<ul class="mt-2 list-disc pl-5 text-sm text-slate-700">
					{#each resultActions as action (action)}
						<li>{actionLabel(action)}</li>
					{/each}
				</ul>
			</div>
		{/if}
		<button class="self-start text-sm font-medium text-teal-700 underline" onclick={resetForm}>
			Submit another report
		</button>
	{:else if step === 'question' && currentEvent}
		<form class="flex flex-col gap-4" onsubmit={handleAnswerSubmit}>
			<div class="rounded-md border border-slate-300 bg-white px-4 py-3">
				<p class="text-sm text-slate-500">You reported:</p>
				<p class="mt-1 text-sm text-slate-800">{currentEvent.raw_text}</p>
			</div>

			<div class="flex flex-col gap-1">
				<label for="answer" class="text-sm font-medium text-slate-800">
					{currentEvent.clarification_question}
				</label>
				<textarea
					id="answer"
					bind:value={answer}
					required
					rows="3"
					class="rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-teal-600 focus:outline-none"
				></textarea>
			</div>

			<div class="flex flex-col gap-1">
				<label for="contact" class="text-sm font-medium text-slate-800">
					Contact details <span class="font-normal text-slate-500">(optional)</span>
				</label>
				<input
					id="contact"
					type="text"
					bind:value={contact}
					placeholder="Email or phone, if you'd like the council to follow up"
					class="rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-teal-600 focus:outline-none"
				/>
			</div>

			{#if errorMessage}
				<p class="text-sm text-red-600">{errorMessage}</p>
			{/if}

			<button
				type="submit"
				disabled={submitting || !answer.trim()}
				class="rounded-md bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:opacity-50"
			>
				{submitting ? 'Sending…' : 'Send answer'}
			</button>
		</form>
	{:else}
		<form class="flex flex-col gap-4" onsubmit={handleReportSubmit}>
			<div class="flex flex-col gap-1">
				<label for="raw_text" class="text-sm font-medium text-slate-800">
					What's happening?
				</label>
				<textarea
					id="raw_text"
					bind:value={rawText}
					required
					rows="5"
					placeholder="e.g. There's a large tree branch down blocking the footpath on Riddiford Street."
					class="rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-teal-600 focus:outline-none"
				></textarea>
			</div>

			<div class="flex flex-col gap-1">
				<label for="suburb" class="text-sm font-medium text-slate-800">
					Suburb
					{#if locationStatus === 'granted'}
						<span class="font-normal text-slate-500">(optional — we've got your location)</span>
					{/if}
				</label>
				<input
					id="suburb"
					type="text"
					bind:value={suburb}
					placeholder="e.g. Newtown"
					class="rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-teal-600 focus:outline-none"
				/>
				{#if locationStatus === 'denied' || locationStatus === 'unsupported'}
					<p class="text-xs text-slate-500">
						Location wasn't available — please enter your suburb so we can match you to nearby
						hazard information.
					</p>
				{/if}
			</div>

			{#if errorMessage}
				<p class="text-sm text-red-600">{errorMessage}</p>
			{/if}

			<button
				type="submit"
				disabled={submitting || !rawText.trim()}
				class="rounded-md bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:opacity-50"
			>
				{submitting ? 'Sending…' : 'Send report'}
			</button>
		</form>
	{/if}
</main>
