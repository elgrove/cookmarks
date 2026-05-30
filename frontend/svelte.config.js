import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA: a single index.html fallback that FastAPI serves in production.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
