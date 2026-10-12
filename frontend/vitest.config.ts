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
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
			// Route tests mount real +page components under plain vitest, so
			// $app/* resolves to small test doubles instead of SvelteKit. The
			// doubles are intentionally minimal — extend them when a route needs
			// more of the $app surface (url, data, invalidate, ...).
			'$app/stores': fileURLToPath(new URL('./src/test-mocks/app-stores.ts', import.meta.url)),
			'$app/navigation': fileURLToPath(
				new URL('./src/test-mocks/app-navigation.ts', import.meta.url)
			)
		}
	},
	test: {
		environment: 'jsdom',
		include: ['src/**/*.{test,spec}.ts']
	}
});
