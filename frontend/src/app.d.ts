// See https://kit.svelte.dev/docs/types#app
declare global {
  namespace App {
    interface Locals {
      user: { id: number; username: string; is_staff: boolean } | null;
      noAuth: boolean;
    }
    interface PageData {
      user?: { id: number; username: string; is_staff: boolean } | null;
      noAuth?: boolean;
    }
  }
}

export {};
