<script lang="ts">
  import { goto } from "$app/navigation";
  import { auth as authApi } from "$api";
  import { isApiError } from "$api/client";

  let username = $state("");
  let password = $state("");
  let error = $state<string | null>(null);
  let submitting = $state(false);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    submitting = true;
    error = null;
    try {
      await authApi.login(username, password);
      await goto("/");
    } catch (e) {
      if (isApiError(e) && e.status === 401) {
        error = "Invalid username or password";
      } else {
        error = "Login failed — please try again";
      }
    } finally {
      submitting = false;
    }
  }
</script>

<div class="container" style="max-width: 24rem;">
  <h1 class="h3 mt-5 mb-4 text-center">cookmarks</h1>
  <form onsubmit={submit} class="card p-4">
    <h2 class="h5 mb-3">Log in</h2>
    {#if error}
      <div class="alert alert-danger py-2">{error}</div>
    {/if}
    <div class="mb-3">
      <label for="username" class="form-label">Username</label>
      <input
        id="username"
        type="text"
        class="form-control"
        bind:value={username}
        required
        autocomplete="username"
      />
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">Password</label>
      <input
        id="password"
        type="password"
        class="form-control"
        bind:value={password}
        required
        autocomplete="current-password"
      />
    </div>
    <button class="btn btn-primary" type="submit" disabled={submitting}>
      {submitting ? "Logging in..." : "Log in"}
    </button>
  </form>
</div>
