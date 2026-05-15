<script lang="ts">
  import { lists as listsApi } from "$api";
  import { goto, invalidateAll } from "$app/navigation";

  let { data } = $props();

  let search = $state(data.search);
  let newName = $state("");
  let busy = $state(false);

  function applySearch() {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    goto(`/lists?${params.toString()}`);
  }

  async function createList(e: SubmitEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    busy = true;
    try {
      const created = await listsApi.create(newName.trim());
      newName = "";
      goto(`/recipes?list=${created.id}`);
    } finally {
      busy = false;
    }
  }

  async function deleteList(id: string, name: string) {
    if (!confirm(`Delete list "${name}"?`)) return;
    await listsApi.remove(id);
    await invalidateAll();
  }
</script>

<header class="d-flex justify-content-between align-items-center mb-3">
  <h1 class="h4 mb-0">Recipe lists</h1>
  <form class="d-flex gap-2" onsubmit={(e) => { e.preventDefault(); applySearch(); }}>
    <input class="form-control form-control-sm" type="search" placeholder="Search lists..." bind:value={search} />
  </form>
</header>

<form class="row g-2 mb-4" onsubmit={createList}>
  <div class="col-auto flex-grow-1">
    <input class="form-control" type="text" placeholder="New list name" bind:value={newName} />
  </div>
  <div class="col-auto">
    <button class="btn btn-primary" type="submit" disabled={busy}>Create</button>
  </div>
</form>

<div class="row g-3">
  {#each data.lists as l}
    <div class="col-md-4">
      <div class="p-3 border rounded">
        <h5 class="mb-1">
          <a href={`/recipes?list=${l.id}`}>{l.name}</a>
          {#if l.is_default}
            <i class="bi bi-star-fill text-warning"></i>
          {/if}
        </h5>
        <div class="text-secondary small">
          {l.recipe_count} recipe{l.recipe_count === 1 ? "" : "s"}
        </div>
        {#if !l.is_default}
          <button
            class="btn btn-sm btn-link p-0 text-danger mt-2"
            onclick={() => deleteList(l.id, l.name)}
          >
            Delete
          </button>
        {/if}
      </div>
    </div>
  {/each}
</div>
