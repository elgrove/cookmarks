<script module lang="ts">
	export type TocEntry = { label: string; href: string; depth: number };
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		title: string;
		author: string;
		backHref: string;
		toc: TocEntry[];
		currentHref?: string | null;
		/** Reading progress through the book, 0–1. */
		progress: number;
		/** Text-size multiplier, e.g. 1 = 100%. */
		fontScale: number;
		theme: 'light' | 'dark';
		onSelectToc: (href: string) => void;
		onPrev: () => void;
		onNext: () => void;
		onFontDec: () => void;
		onFontInc: () => void;
		onToggleTheme: () => void;
		children?: Snippet;
	};

	let {
		title,
		author,
		backHref,
		toc,
		currentHref = null,
		progress,
		fontScale,
		theme,
		onSelectToc,
		onPrev,
		onNext,
		onFontDec,
		onFontInc,
		onToggleTheme,
		children
	}: Props = $props();

	// The drawer is self-contained so the unit is verifiable in isolation: clicking the
	// Contents button is enough to open it, without a parent threading state back in.
	let tocOpen = $state(false);

	let pct = $derived(Math.max(0, Math.min(100, Math.round(progress * 100))));
	let fontPct = $derived(Math.round(fontScale * 100));
	let currentLabel = $derived(toc.find((t) => t.href === currentHref)?.label ?? '');

	function selectToc(href: string) {
		tocOpen = false;
		onSelectToc(href);
	}
</script>

<div
	class="reader"
	data-verify-unit="reader-chrome"
	data-verify-toc-count={toc.length}
	data-verify-progress={pct}
	data-verify-toc-open={tocOpen ? 'true' : 'false'}
	data-verify-font-scale={fontPct}
>
	<header class="bar top">
		<a class="back" href={backHref} aria-label="Back to book details">
			<span class="ar" aria-hidden="true">‹</span> Book
		</a>

		<div class="title">
			<span class="t">{title}</span>
			{#if author}<span class="by">{author}</span>{/if}
		</div>

		<div class="controls">
			<button
				class="ctl"
				type="button"
				aria-label="Table of contents"
				aria-expanded={tocOpen}
				onclick={() => (tocOpen = !tocOpen)}>Contents</button
			>
			<span class="fontset" role="group" aria-label="Text size">
				<button class="ctl icon" type="button" aria-label="Decrease text size" onclick={onFontDec}
					>A−</button
				>
				<span class="fontval mono" aria-hidden="true">{fontPct}%</span>
				<button class="ctl icon" type="button" aria-label="Increase text size" onclick={onFontInc}
					>A+</button
				>
			</span>
			<button class="ctl icon" type="button" aria-label="Toggle light or dark theme" onclick={onToggleTheme}
				>{theme === 'dark' ? '☾' : '☀'}</button
			>
		</div>
	</header>

	<div class="progress" role="presentation">
		<div class="fill" style:width={`${pct}%`}></div>
	</div>

	<main class="viewport">
		{@render children?.()}
	</main>

	{#if tocOpen}
		<button class="scrim" type="button" aria-label="Close contents" onclick={() => (tocOpen = false)}
		></button>
		<aside class="drawer" aria-label="Table of contents">
			<p class="label">Contents</p>
			{#if toc.length}
				<nav class="toc">
					{#each toc as item, i (i)}
						<button
							class="toc-item"
							class:current={item.href === currentHref}
							type="button"
							style:--depth={item.depth}
							onclick={() => selectToc(item.href)}>{item.label}</button
						>
					{/each}
				</nav>
			{:else}
				<p class="toc-empty">No contents listed in this book.</p>
			{/if}
		</aside>
	{/if}

	<footer class="bar bottom">
		<button class="page" type="button" aria-label="Previous page" onclick={onPrev}>
			<span class="ar" aria-hidden="true">‹</span> Prev
		</button>
		<div class="loc mono">
			{#if currentLabel}<span class="chap">{currentLabel}</span>
				<span class="dot" aria-hidden="true">·</span>{/if}
			<span class="pct">{pct}%</span>
		</div>
		<button class="page" type="button" aria-label="Next page" onclick={onNext}>
			Next <span class="ar" aria-hidden="true">›</span>
		</button>
	</footer>
</div>

<style>
	.reader {
		display: flex;
		flex-direction: column;
		height: 100dvh;
		background: var(--bg);
		color: var(--ink);
		overflow: hidden;
	}

	.bar {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0 clamp(1rem, 4vw, 2.5rem);
		flex: none;
		background: var(--bg);
	}
	.bar.top {
		height: 3.4rem;
		border-bottom: var(--border);
		/* Equal side columns so the title is centred against the bar, not the gap between buttons. */
		display: grid;
		grid-template-columns: 1fr minmax(0, auto) 1fr;
	}
	.bar.bottom {
		height: 3rem;
		border-top: var(--border);
		justify-content: space-between;
	}

	.back {
		justify-self: start;
		font-family: var(--f-grotesk);
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--muted);
		text-decoration: none;
		white-space: nowrap;
		transition: color 0.18s var(--ease-out);
	}
	.back:hover {
		color: var(--clay-deep);
	}

	.title {
		justify-self: center;
		min-width: 0;
		max-width: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		line-height: 1.15;
	}
	.title .t {
		font-family: var(--f-serif);
		font-style: italic;
		font-size: 1rem;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.title .by {
		font-family: var(--f-mono);
		font-size: 0.62rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--faint);
	}

	.controls {
		justify-self: end;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.fontset {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.fontval {
		font-size: 0.66rem;
		color: var(--faint);
		min-width: 2.4em;
		text-align: center;
	}
	.ctl {
		font-family: var(--f-grotesk);
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--ink);
		background: transparent;
		border: 1px solid var(--line-strong);
		border-radius: 3px;
		padding: 0.32rem 0.6rem;
		cursor: pointer;
		transition:
			border-color 0.18s var(--ease-out),
			color 0.18s var(--ease-out);
	}
	.ctl.icon {
		padding: 0.32rem 0.5rem;
		min-width: 2rem;
	}
	.ctl:hover {
		border-color: var(--clay);
		color: var(--clay-deep);
	}

	.progress {
		flex: none;
		height: 2px;
		background: var(--line);
	}
	.progress .fill {
		height: 100%;
		background: var(--clay);
		transition: width 0.3s var(--ease-out);
	}

	.viewport {
		flex: 1;
		min-height: 0;
		position: relative;
		overflow: hidden;
	}

	.scrim {
		position: absolute;
		inset: 0;
		border: none;
		padding: 0;
		background: color-mix(in srgb, var(--ink) 24%, transparent);
		cursor: pointer;
		z-index: 1;
	}
	.drawer {
		position: absolute;
		top: 0;
		left: 0;
		bottom: 0;
		width: min(22rem, 84vw);
		background: var(--bg);
		border-right: var(--border-strong);
		padding: 1.5rem 1.2rem 2rem;
		overflow-y: auto;
		z-index: 2;
		animation: slideIn 0.28s var(--ease-out) both;
	}
	@keyframes slideIn {
		from {
			transform: translateX(-100%);
		}
		to {
			transform: translateX(0);
		}
	}
	.label {
		font-family: var(--f-mono);
		font-size: 0.65rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--muted);
		margin: 0 0 0.9rem;
	}
	.toc {
		display: flex;
		flex-direction: column;
	}
	.toc-item {
		font-family: var(--f-serif);
		font-size: 0.98rem;
		line-height: 1.35;
		text-align: left;
		color: var(--ink);
		background: transparent;
		border: none;
		border-top: var(--border);
		padding: 0.6rem 0 0.6rem calc(var(--depth, 0) * 0.9rem);
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}
	.toc-item:first-child {
		border-top: none;
	}
	.toc-item:hover {
		color: var(--clay-deep);
	}
	.toc-item.current {
		color: var(--clay-deep);
		font-style: italic;
	}
	.toc-empty {
		font-family: var(--f-serif);
		font-style: italic;
		color: var(--muted);
		margin: 0;
	}

	.page {
		font-family: var(--f-grotesk);
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--ink);
		background: transparent;
		border: none;
		padding: 0.4rem 0.5rem;
		cursor: pointer;
		transition: color 0.18s var(--ease-out);
	}
	.page:hover {
		color: var(--clay-deep);
	}
	.loc {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		color: var(--muted);
		min-width: 0;
	}
	.loc .chap {
		max-width: 48vw;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.loc .pct {
		color: var(--ink);
	}

	@media (prefers-reduced-motion: reduce) {
		.drawer {
			animation: none;
		}
		.progress .fill {
			transition: none;
		}
	}
</style>
