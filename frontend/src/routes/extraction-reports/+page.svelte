<script lang="ts">
  import { extraction } from "$api";
  import { invalidateAll } from "$app/navigation";

  let { data } = $props();
  let { bundle } = $derived(data);
  let busy = $state<Record<string, boolean>>({});
  let toast = $state<string | null>(null);

  function flash(msg: string) {
    toast = msg;
    setTimeout(() => (toast = null), 3000);
  }

  async function resume(id: string, response: "has_images" | "no_images") {
    busy = { ...busy, [id]: true };
    try {
      const res = await extraction.resume(id, response);
      flash(res.detail);
      await invalidateAll();
    } finally {
      busy = { ...busy, [id]: false };
    }
  }

  function fmtDuration(start: string | null, end: string | null): string {
    if (!start || !end) return "—";
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    const secs = Math.round((e - s) / 1000);
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  }
</script>

<header class="mb-3">
  <h1 class="h4">Extraction reports</h1>
  <p class="text-secondary mb-0">
    {bundle.processed_books}/{bundle.total_books} books processed ·
    {bundle.total_recipes} recipes ·
    ${bundle.total_cost} in the last 14 days
  </p>
</header>

{#if !bundle.provider_configured}
  <div class="alert alert-warning">
    No AI provider configured. Set one up on the
    <a href="/config" class="alert-link">Config page</a>.
  </div>
{/if}

{#if toast}
  <div class="alert alert-info">{toast}</div>
{/if}

<div class="table-responsive">
  <table class="table table-sm align-middle">
    <thead>
      <tr>
        <th>Book</th>
        <th>Status</th>
        <th>Method</th>
        <th>Chapters</th>
        <th>Recipes</th>
        <th>Images</th>
        <th>Cost</th>
        <th>Duration</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each bundle.reports as r}
        <tr>
          <td>
            <a href={`/books/${r.book_id}`}>{r.book_clean_title}</a>
            <div class="text-secondary small">{r.book_author}</div>
          </td>
          <td>
            <span
              class="badge bg-{r.status === 'done' ? 'success' : r.status === 'review' ? 'warning' : 'secondary'}"
            >
              {r.status}
            </span>
          </td>
          <td>{r.extraction_method ?? "—"}</td>
          <td>{r.chapters_processed_count}/{r.total_chapters}</td>
          <td>{r.recipes_found}</td>
          <td>{r.image_count}</td>
          <td>{r.cost_usd ? `$${r.cost_usd}` : "—"}</td>
          <td>{fmtDuration(r.started_at, r.completed_at)}</td>
          <td>
            {#if r.status === "review"}
              <div class="btn-group btn-group-sm" role="group">
                <button
                  class="btn btn-outline-success"
                  disabled={busy[r.id]}
                  onclick={() => resume(r.id, "has_images")}
                >
                  Has images
                </button>
                <button
                  class="btn btn-outline-secondary"
                  disabled={busy[r.id]}
                  onclick={() => resume(r.id, "no_images")}
                >
                  No images
                </button>
              </div>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
