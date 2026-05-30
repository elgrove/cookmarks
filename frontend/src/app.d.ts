import type { VerifyHandle } from '$lib/verify/types';

declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
	}

	interface Window {
		__verify?: VerifyHandle;
	}
}

export {};
