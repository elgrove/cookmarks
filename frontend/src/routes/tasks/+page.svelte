<script lang="ts">
  import { tasks as tasksApi } from "$api";

  let { data } = $props();
  let { overview } = $derived(data);

  let busy = $state(false);
  let toast = $state<string | null>(null);
  let randomCount = $state(10);
  let randomMethod = $state<string>("");
  let allMethod = $state<string>("");

  function flash(msg: string) {
    toast = msg;
    setTimeout(() => (toast = null), 3000);
  }

  async function loadBooks() {
    busy = true;
    try {
      flash((await tasksApi.loadBooks()).detail);
    } finally {
      busy = false;
    }
  }

  async function dedupeKeywords() {
    busy = true;
    try {
      flash((await tasksApi.dedupeKeywords()).detail);
    } finally {
      busy = false;
    }
  }

  async function queueAll() {
    if (!confirm(`Queue all ${overview.books_count} books for extraction?`)) return;
    busy = true;
    try {
      flash((await tasksApi.queueAllExtractions(allMethod || undefined)).detail);
    } finally {
      busy = false;
    }
  }

  async function queueRandom() {
    busy = true;
    try {
      flash(
        (await tasksApi.queueRandomExtractions(randomCount, randomMethod || undefined)).detail,
      );
    } finally {
      busy = false;
    }
  }
</script>

<header class="mb-4">
  <h1 class="h4">Tasks</h1>
  <p class="text-secondary">
    {overview.books_count} books in library, {overview.books_with_recipes_count} with recipes.
  </p>
</header>

{#if toast}
  <div class="alert alert-info">{toast}</div>
{/if}

<div class="row g-3">
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Load books from Calibre</h5>
        <p class="card-text text-secondary">
          Scan the Calibre library and create or update Book records.
        </p>
        <button class="btn btn-primary" disabled={busy} onclick={loadBooks}>
          Queue
        </button>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Deduplicate keywords</h5>
        <p class="card-text text-secondary">
          Normalize and merge similar keywords across all recipes.
        </p>
        <button class="btn btn-primary" disabled={busy} onclick={dedupeKeywords}>
          Queue
        </button>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Extract from random books</h5>
        <p class="card-text text-secondary">
          Queue N books without recipes for extraction.
        </p>
        <div class="row g-2">
          <div class="col">
            <input
              class="form-control form-control-sm"
              type="number"
              min="1"
              max="1000"
              bind:value={randomCount}
            />
          </div>
          <div class="col">
            <select class="form-select form-select-sm" bind:value={randomMethod}>
              <option value="">Auto method</option>
              <option value="file">File</option>
              <option value="block">Block</option>
            </select>
          </div>
        </div>
        <button class="btn btn-primary mt-2" disabled={busy} onclick={queueRandom}>
          Queue {randomCount}
        </button>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Extract from all books</h5>
        <p class="card-text text-secondary">
          Queue every book in the library. Be mindful of API costs.
        </p>
        <select class="form-select form-select-sm mb-2" bind:value={allMethod}>
          <option value="">Auto method</option>
          <option value="file">File</option>
          <option value="block">Block</option>
        </select>
        <button class="btn btn-warning" disabled={busy} onclick={queueAll}>
          Queue all
        </button>
      </div>
    </div>
  </div>
</div>
