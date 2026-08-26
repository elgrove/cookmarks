import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	// foliate's PDF engine loads pdfjs with a top-level await, which the default target
	// predates.
	build: { target: 'es2022' },
	server: {
		host: '0.0.0.0',
		// Defaults match the standard dev setup; override to run worktrees side by side.
		port: Number(process.env.VITE_DEV_PORT) || 9789,
		proxy: {
			'/api': process.env.VITE_API_PROXY || 'http://localhost:9788'
		}
	}
});
