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

// What a reply is allowed to be: the Markdown subset, and nothing else. An allow-list
// rather than a deny-list because the reply is rendered as HTML inside the app's own
// chrome — subtracting the tags that look dangerous still leaves <form>, style
// attributes and the rest, which is a phishing surface even without script execution.
// Images are out too: the assistant deals in prose and links, and a model-supplied
// <img> is an alt-less remote fetch nobody asked for.
const ALLOWED_TAGS = [
	'p', 'br', 'hr', 'em', 'strong', 'del', 'code', 'pre', 'blockquote',
	'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
	'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
];
const ALLOWED_ATTR = ['href', 'title'];

/** Render an assistant reply. The text comes from a model, so it is Markdown at best
 *  and hostile HTML at worst. Without a DOM to sanitise against, it is escaped rather
 *  than trusted. */
export function renderMarkdown(text: string): string {
	if (!DOMPurify.isSupported) return escape(text);
	return internalise(
		DOMPurify.sanitize(marked.parse(text, { async: false, breaks: true }), {
			ALLOWED_TAGS,
			ALLOWED_ATTR
		})
	);
}

const INTERNAL_PATH = /^\/?(recipes|books|lists)\/[^/?#]+$/;

/** Pull app links back inside the app. Told to write `/recipes/{id}`, a model will
 *  sometimes put a hostname of its own invention in front of it, and sometimes drop the
 *  leading slash — one link leaves the app, the other resolves against whatever page it
 *  happens to be read on. Both are repaired here, where the shape of an app link is known. */
function internalise(html: string): string {
	const doc = new DOMParser().parseFromString(html, 'text/html');
	for (const link of doc.querySelectorAll('a[href]')) {
		const path = (link.getAttribute('href') ?? '').replace(/^https?:\/\/[^/]+/i, '');
		if (INTERNAL_PATH.test(path))
			link.setAttribute('href', path.startsWith('/') ? path : `/${path}`);
	}
	return doc.body.innerHTML;
}
