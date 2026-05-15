<script lang="ts">
  import { config as configApi } from "$api";

  let { data } = $props();

  let provider = $state(data.config.ai_provider);
  let apiKey = $state("");
  let rateLimit = $state(data.config.extraction_rate_limit_per_minute);
  let saved = $state(false);
  let busy = $state(false);

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    saved = false;
    try {
      await configApi.update({
        ai_provider: provider,
        api_key: apiKey || undefined,
        extraction_rate_limit_per_minute: rateLimit,
      });
      saved = true;
      apiKey = "";
    } finally {
      busy = false;
    }
  }
</script>

<header class="mb-3">
  <h1 class="h4">Config</h1>
</header>

<form class="col-md-6" onsubmit={save}>
  {#if saved}
    <div class="alert alert-success py-2">Configuration saved.</div>
  {/if}

  <div class="mb-3">
    <label class="form-label">AI provider</label>
    <select class="form-select" bind:value={provider}>
      <option value="">— Choose —</option>
      <option value="GEMINI">Google Gemini</option>
      <option value="OPENROUTER">OpenRouter</option>
      <option value="STUB">Stub (offline / dev)</option>
    </select>
  </div>

  <div class="mb-3">
    <label class="form-label">API key</label>
    <input
      class="form-control"
      type="password"
      bind:value={apiKey}
      placeholder={data.config.has_api_key ? data.config.api_key_masked : "Enter a key"}
    />
    {#if data.config.has_api_key}
      <div class="form-text">Leave blank to keep the existing key.</div>
    {/if}
  </div>

  <div class="mb-3">
    <label class="form-label">Extraction rate limit (per minute)</label>
    <input class="form-control" type="number" min="1" bind:value={rateLimit} />
  </div>

  <button class="btn btn-primary" type="submit" disabled={busy}>
    {busy ? "Saving..." : "Save"}
  </button>
</form>
