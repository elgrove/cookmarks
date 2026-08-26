import DOMPurify from 'dompurify';
import { marked } from 'marked';

const ESCAPES: Record<string, string> = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#39;'
};

function escape(text: string): string {
	return text.replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

/** Render an assistant reply. The text comes from a model, so it is Markdown at best
 *  and hostile HTML at worst: parse it, then strip anything that can execute. Images go
 *  too — the assistant deals in prose and links, and a model-supplied <img> is an
 *  alt-less remote fetch nobody asked for. Without a DOM to sanitise against, the text
 *  is escaped rather than trusted. */
export function renderMarkdown(text: string): string {
	if (!DOMPurify.isSupported) return escape(text);
	return DOMPurify.sanitize(marked.parse(text, { async: false, breaks: true }), {
		FORBID_TAGS: ['img', 'style']
	});
}

/** Whether a link points inside the app, so the UI can route it rather than leave. */
export function isInternalLink(href: string): boolean {
	return href.startsWith('/recipes/') || href.startsWith('/books/') || href.startsWith('/lists/');
}
