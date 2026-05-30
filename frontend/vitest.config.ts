import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Standalone test config: the plain svelte() plugin (not sveltekit) compiles
// components for jsdom, so harness tests stay free of SvelteKit app coupling.
export default defineConfig({
	plugins: [svelte()],
	resolve: {
		// Resolve Svelte's client build so mount()/unmount() work under jsdom.
		conditions: ['browser'],
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url))
		}
	},
	test: {
		environment: 'jsdom',
		include: ['src/**/*.{test,spec}.ts']
	}
});
