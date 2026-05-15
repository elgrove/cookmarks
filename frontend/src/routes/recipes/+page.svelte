<script lang="ts">
  import { recipes as recipesApi } from "$api";
  import RecipeCard from "$components/RecipeCard.svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";

  let { data } = $props();

  let q = $state(data.state.q);
  let aiPrompt = $state("");
  let aiBusy = $state(false);
  let aiError = $state<string | null>(null);

  let sort = $state(data.state.sort);
  let groupLogic = $state<"and" | "or">(data.state.group_logic as "and" | "or");
  let selectedLists = $state<string[]>(data.state.selected_lists);
  let selectedKeywords = $state<string[]>(data.state.selected_keywords);
  let filters = $state(data.state.filters);
  let keywordSearch = $state("");
  let listSearch = $state("");

  const filteredKeywords = $derived(
    keywordSearch
      ? data.allKeywords.filter((k) =>
          k.name.toLowerCase().includes(keywordSearch.toLowerCase()),
        )
      : data.allKeywords.slice(0, 50),
  );

  const filteredLists = $derived(
    listSearch
      ? data.allLists.filter((l) =>
          l.name.toLowerCase().includes(listSearch.toLowerCase()),
        )
      : data.allLists,
  );

  function addFilter() {
    filters = [
      ...filters,
      { field: "name", op: "contains", value: "", group: 0, logic: "or" },
    ];
  }

  function removeFilter(idx: number) {
    filters = filters.filter((_, i) => i !== idx);
  }

  function buildParams(extra: Record<string, string | undefined> = {}): URLSearchParams {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (sort) params.set("sort", sort);
    params.set("group_logic", groupLogic);
    for (const l of selectedLists) params.append("selected_lists", l);
    for (const k of selectedKeywords) params.append("selected_keywords", k);
    if (data.state.vector_search) params.set("vector_search", data.state.vector_search);
    for (const f of filters) {
      if (!f.value.trim()) continue;
      params.append("filter_field", f.field);
      params.append("filter_op", f.op);
      params.append("filter_value", f.value);
      params.append("filter_group", String(f.group));
      params.append("filter_logic", f.logic);
    }
    for (const [k, v] of Object.entries(extra)) if (v !== undefined) params.set(k, v);
    return params;
  }

  function apply() {
    const params = buildParams();
    params.delete("page");
    goto(`/recipes?${params.toString()}`);
  }

  function clearVectorSearch() {
    const params = new URLSearchParams(page.url.searchParams);
    params.delete("vector_search");
    goto(`/recipes?${params.toString()}`);
  }

  function gotoPage(n: number) {
    const params = new URLSearchParams(page.url.searchParams);
    params.set("page", String(n));
    goto(`/recipes?${params.toString()}`);
  }

  async function runAiSearch() {
    if (!aiPrompt.trim()) return;
    aiBusy = true;
    aiError = null;
    try {
      const res = await recipesApi.aiSearch(aiPrompt.trim());
      const params = buildParams({ vector_search: res.search_key, sort: "relevance" });
      params.delete("page");
      goto(`/recipes?${params.toString()}`);
    } catch (e) {
      aiError = e instanceof Error ? e.message : "AI search failed";
    } finally {
      aiBusy = false;
    }
  }

  const contextParams = $derived(
    (() => {
      const params = new URLSearchParams();
      params.set("context", "search");
      if (q) params.set("q", q);
      if (sort) params.set("sort", sort);
      if (data.state.vector_search) params.set("vector_search", data.state.vector_search);
      for (const l of selectedLists) params.append("selected_lists", l);
      for (const f of filters) {
        if (!f.value.trim()) continue;
        params.append("filter_field", f.field);
        params.append("filter_op", f.op);
        params.append("filter_value", f.value);
        params.append("filter_group", String(f.group));
        params.append("filter_logic", f.logic);
      }
      return params.toString();
    })(),
  );
</script>

<div class="row g-4">
  <aside class="col-lg-3 sidebar">
    <form onsubmit={(e) => { e.preventDefault(); apply(); }}>
      <div class="mb-3">
        <label class="form-label">Quick search</label>
        <input class="form-control" type="text" bind:value={q} placeholder="Name, ingredient, book..." />
      </div>

      <div class="mb-4 border-bottom pb-3">
        <label class="form-label">AI search</label>
        <input
          class="form-control mb-2"
          type="text"
          bind:value={aiPrompt}
          placeholder="What are you in the mood for?"
        />
        <button
          type="button"
          class="btn btn-sm btn-outline-primary w-100"
          disabled={aiBusy}
          onclick={runAiSearch}
        >
          {aiBusy ? "Searching..." : "Search semantically"}
        </button>
        {#if aiError}
          <div class="text-danger small mt-1">{aiError}</div>
        {/if}
        {#if data.state.vector_search}
          <button
            type="button"
            class="btn btn-sm btn-link p-0 mt-2"
            onclick={clearVectorSearch}
          >
            Clear AI search
          </button>
        {/if}
      </div>

      <div class="mb-3">
        <label class="form-label">Sort</label>
        <select class="form-select" bind:value={sort}>
          <option value="">Auto</option>
          <option value="name">Name</option>
          <option value="recent">Recent</option>
          <option value="author">Author</option>
          <option value="book">Book</option>
          <option value="order">Book order</option>
          <option value="random">Random</option>
          {#if data.state.vector_search}
            <option value="relevance">Relevance</option>
          {/if}
        </select>
      </div>

      <div class="mb-3">
        <label class="form-label">Lists</label>
        <input
          class="form-control form-control-sm mb-2"
          type="text"
          bind:value={listSearch}
          placeholder="Filter list..."
        />
        <select class="form-select" multiple size="6" bind:value={selectedLists}>
          {#each filteredLists as l}
            <option value={l.id}>{l.name} ({l.recipe_count})</option>
          {/each}
        </select>
      </div>

      <div class="mb-3">
        <label class="form-label">Keywords</label>
        <input
          class="form-control form-control-sm mb-2"
          type="text"
          bind:value={keywordSearch}
          placeholder="Filter list..."
        />
        <select
          class="form-select"
          multiple
          size="8"
          bind:value={selectedKeywords}
        >
          {#each filteredKeywords as k}
            <option value={k.name}>{k.name} ({k.recipe_count})</option>
          {/each}
        </select>
      </div>

      <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <label class="form-label mb-0">Advanced filters</label>
          <button type="button" class="btn btn-sm btn-link p-0" onclick={addFilter}>
            + Add
          </button>
        </div>
        {#if filters.length > 0}
          <div class="mb-2">
            <select class="form-select form-select-sm" bind:value={groupLogic}>
              <option value="or">Match ANY group (OR)</option>
              <option value="and">Match ALL groups (AND)</option>
            </select>
          </div>
        {/if}
        {#each filters as f, i}
          <div class="border rounded p-2 mb-2">
            <div class="d-flex gap-1 mb-1">
              <select class="form-select form-select-sm" bind:value={f.field}>
                <option value="name">Name</option>
                <option value="description">Description</option>
                <option value="ingredients">Ingredients</option>
                <option value="instructions">Instructions</option>
                <option value="keywords">Keyword</option>
                <option value="author">Author</option>
                <option value="book">Book</option>
              </select>
              <select class="form-select form-select-sm" bind:value={f.op}>
                <option value="contains">contains</option>
                <option value="not_contains">excludes</option>
                <option value="equals">equals</option>
                <option value="starts">starts with</option>
              </select>
            </div>
            <div class="d-flex gap-1">
              <input
                class="form-control form-control-sm"
                type="text"
                bind:value={f.value}
              />
              <button
                type="button"
                class="btn btn-sm btn-outline-secondary"
                onclick={() => removeFilter(i)}
                aria-label="Remove filter"
              >
                ×
              </button>
            </div>
          </div>
        {/each}
      </div>

      <button class="btn btn-primary w-100" type="submit">Apply</button>
    </form>
  </aside>

  <section class="col-lg-9">
    <header class="d-flex justify-content-between align-items-baseline mb-3">
      <h1 class="h4 mb-0">Recipes</h1>
      <span class="text-secondary">{data.results.total} matches</span>
    </header>

    {#if data.state.vector_search}
      <div class="alert alert-info py-2">
        <i class="bi bi-stars"></i>
        Showing AI search results
      </div>
    {/if}

    {#if data.results.total === 0}
      <div class="text-center text-secondary py-5">
        <p>No recipes match — try a different query or add a filter.</p>
      </div>
    {:else}
      <div class="row row-cols-2 row-cols-md-3 row-cols-xl-4 g-3">
        {#each data.results.items as r}
          <div class="col">
            <RecipeCard recipe={r} contextParams={contextParams} />
          </div>
        {/each}
      </div>

      {#if data.results.pages > 1}
        <nav class="d-flex justify-content-center mt-4">
          <ul class="pagination">
            <li class="page-item" class:disabled={!data.results.has_previous}>
              <button class="page-link" onclick={() => gotoPage(data.results.page - 1)}>
                Previous
              </button>
            </li>
            <li class="page-item disabled">
              <span class="page-link">
                {data.results.page} of {data.results.pages}
              </span>
            </li>
            <li class="page-item" class:disabled={!data.results.has_next}>
              <button class="page-link" onclick={() => gotoPage(data.results.page + 1)}>
                Next
              </button>
            </li>
          </ul>
        </nav>
      {/if}
    {/if}
  </section>
</div>
