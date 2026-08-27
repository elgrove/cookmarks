import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
	it('renders Markdown', () => {
		expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
	});

	it('strips scripts, inline handlers and javascript: links', () => {
		const html = renderMarkdown(
			'<script>evil()<\/script><img src="x" onerror="evil()"><a href="javascript:evil()">go</a>'
		);
		expect(html).not.toContain('<script');
		expect(html).not.toContain('onerror');
		expect(html).not.toContain('javascript:');
	});

	it('drops images entirely — the assistant deals in prose and links', () => {
		expect(renderMarkdown('![a dish](/some.jpg)')).not.toContain('<img');
	});

	it('drops a form, so a reply cannot pose as a Cookmarks login', () => {
		const html = renderMarkdown(
			'<form action="https://evil.example/"><input name="password"><button>Sign in</button></form>'
		);
		expect(html).not.toContain('<form');
		expect(html).not.toContain('<input');
		expect(html).not.toContain('<button');
	});

	it('drops style attributes, so a reply cannot cover the page', () => {
		const html = renderMarkdown('<p style="position:fixed;inset:0;background:red">gotcha</p>');
		expect(html).not.toContain('style=');
	});

	it('keeps the Markdown it is supposed to render', () => {
		const html = renderMarkdown('# Title\n\n- one\n- two\n\n`code`');
		expect(html).toContain('<h1>');
		expect(html).toContain('<li>');
		expect(html).toContain('<code>');
	});

	it('pulls an invented hostname off an app link', () => {
		const html = renderMarkdown('[Soup](https://cookmarks.example/recipes/abc-123)');
		expect(html).toContain('href="/recipes/abc-123"');
	});

	it('puts back a leading slash the model dropped', () => {
		const html = renderMarkdown('[Soup](recipes/abc-123)');
		expect(html).toContain('href="/recipes/abc-123"');
	});

	it('leaves a genuine external link alone', () => {
		const html = renderMarkdown('[BBC](https://bbc.co.uk/food)');
		expect(html).toContain('href="https://bbc.co.uk/food"');
	});
});
