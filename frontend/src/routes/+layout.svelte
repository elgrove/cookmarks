<script lang="ts">
  import "bootstrap/dist/css/bootstrap.min.css";
  import "bootstrap-icons/font/bootstrap-icons.css";
  import "../app.css";
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { auth as authApi } from "$api";

  let { data, children } = $props();

  onMount(async () => {
    // Bootstrap JS only runs in the browser; load it dynamically so SSR
    // doesn't try to evaluate it.
    await import("bootstrap/dist/js/bootstrap.bundle.min.js");
  });

  $effect(() => {
    if (data.requireLogin && page.url.pathname !== "/login") {
      goto("/login");
    }
  });

  async function logout() {
    await authApi.logout();
    await goto("/login");
  }

  const adminPaths = ["/tasks", "/extraction-reports", "/config"];
  const isAdminActive = $derived(adminPaths.includes(page.url.pathname));
</script>

<nav class="navbar navbar-expand-lg bg-body-tertiary border-bottom mb-3">
  <div class="container-fluid">
    <a class="navbar-brand fw-bold" href="/">cookmarks</a>
    <button
      class="navbar-toggler"
      type="button"
      data-bs-toggle="collapse"
      data-bs-target="#nav"
    >
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="nav">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="/books">Books</a></li>
        <li class="nav-item">
          <a class="nav-link" href="/recipes">Recipes</a>
        </li>
        <li class="nav-item"><a class="nav-link" href="/lists">Lists</a></li>
        <li class="nav-item dropdown">
          <button
            class="nav-link dropdown-toggle"
            class:active={isAdminActive}
            type="button"
            data-bs-toggle="dropdown"
            aria-expanded="false"
          >
            Admin
          </button>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="/tasks">Tasks</a></li>
            <li>
              <a class="dropdown-item" href="/extraction-reports">Reports</a>
            </li>
            <li><a class="dropdown-item" href="/config">Config</a></li>
          </ul>
        </li>
      </ul>
      {#if data.user && !data.noAuth}
        <span class="text-muted small me-3">{data.user.username}</span>
        <button class="btn btn-sm btn-outline-secondary" onclick={logout}>
          Log out
        </button>
      {/if}
    </div>
  </div>
</nav>

<main class="container-fluid pb-5">
  {@render children?.()}
</main>
