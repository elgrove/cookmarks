<script lang="ts">
  import { recipes as recipesApi, lists as listsApi } from "$api";
  import { goto, invalidateAll } from "$app/navigation";

  let { data } = $props();
  const { recipe, allLists, contextQuery } = data;

  let isFavourite = $state(recipe.is_favourite);
  let listIds = $state<string[]>(recipe.list_ids);
  let keywordsInput = $state(recipe.keywords.join(", "));
  let busy = $state(false);
  let editingKeywords = $state(false);
  let newListName = $state("");
  let toast = $state<string | null>(null);

  function flash(msg: string) {
    toast = msg;
    setTimeout(() => (toast = null), 3000);
  }

  function imageSrc(): string | null {
    if (!recipe.image) return null;
    if (recipe.image.startsWith("data:") || recipe.image.startsWith("http")) {
      return recipe.image;
    }
    return recipesApi.imageUrl(recipe.book_id, recipe.image);
  }

  async function toggleFav() {
    const res = await recipesApi.toggleFavourite(recipe.id);
    isFavourite = res.is_favourite;
  }

  async function saveKeywords() {
    busy = true;
    try {
      const names = keywordsInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await recipesApi.setKeywords(recipe.id, names);
      editingKeywords = false;
      flash("Keywords updated");
      await invalidateAll();
    } finally {
      busy = false;
    }
  }

  async function addToList(listId: string) {
    await listsApi.addRecipe(listId, recipe.id);
    if (!listIds.includes(listId)) listIds = [...listIds, listId];
  }

  async function removeFromList(listId: string) {
    await listsApi.removeRecipe(listId, recipe.id);
    listIds = listIds.filter((id) => id !== listId);
  }

  async function createListAndAdd() {
    if (!newListName.trim()) return;
    busy = true;
    try {
      const created = await listsApi.create(newListName.trim());
      await listsApi.addRecipe(created.id, recipe.id);
      newListName = "";
      flash(`Added to "${created.name}"`);
      await invalidateAll();
    } finally {
      busy = false;
    }
  }

  async function deleteRecipe() {
    if (!confirm(`Delete "${recipe.name}"?`)) return;
    await recipesApi.remove(recipe.id);
    goto(`/books/${recipe.book_id}`);
  }

  async function clearImage() {
    if (!confirm("Remove image from this recipe?")) return;
    await recipesApi.clearImage(recipe.id);
    await invalidateAll();
  }

  function neighbourHref(id: string): string {
    return `/recipes/${id}${contextQuery ? `?${contextQuery}` : ""}`;
  }

  const availableLists = $derived(
    allLists.filter((l) => !listIds.includes(l.id)),
  );
  const currentLists = $derived(
    allLists.filter((l) => listIds.includes(l.id)),
  );
</script>

<nav aria-label="breadcrumb" class="mb-3">
  <ol class="breadcrumb mb-0">
    {#if recipe.breadcrumb?.type === "book"}
      <li class="breadcrumb-item"><a href="/books">Books</a></li>
      <li class="breadcrumb-item">
        <a href={`/books/${recipe.breadcrumb.book_id}`}>
          {recipe.breadcrumb.book_title}
        </a>
      </li>
    {:else if recipe.breadcrumb?.type === "list"}
      <li class="breadcrumb-item"><a href="/lists">Lists</a></li>
      <li class="breadcrumb-item">
        <a href={`/recipes?list=${recipe.breadcrumb.list_id}`}>
          {recipe.breadcrumb.list_name}
        </a>
      </li>
    {:else}
      <li class="breadcrumb-item"><a href="/recipes">Recipes</a></li>
    {/if}
    <li class="breadcrumb-item active">{recipe.clean_name}</li>
  </ol>
</nav>

{#if toast}
  <div class="alert alert-info">{toast}</div>
{/if}

<div class="d-flex justify-content-between align-items-center mb-3">
  <div class="d-flex gap-2">
    {#if recipe.previous_recipe}
      <a class="btn btn-sm btn-outline-secondary" href={neighbourHref(recipe.previous_recipe.id)}>
        <i class="bi bi-chevron-left"></i>
        {recipe.previous_recipe.clean_name}
      </a>
    {/if}
  </div>
  <div class="d-flex gap-2">
    {#if recipe.next_recipe}
      <a class="btn btn-sm btn-outline-secondary" href={neighbourHref(recipe.next_recipe.id)}>
        {recipe.next_recipe.clean_name}
        <i class="bi bi-chevron-right"></i>
      </a>
    {/if}
  </div>
</div>

<article class="row g-4">
  <div class="col-md-5">
    {#if imageSrc()}
      <img src={imageSrc()} alt={recipe.name} class="cover mb-2" />
      <button class="btn btn-sm btn-link text-secondary" onclick={clearImage}>
        Remove image
      </button>
    {/if}
    <div class="d-flex gap-2 mb-3">
      <button
        class="btn btn-outline-{isFavourite ? 'danger' : 'secondary'}"
        onclick={toggleFav}
        aria-pressed={isFavourite}
      >
        <i class="bi bi-heart{isFavourite ? '-fill' : ''}"></i>
        {isFavourite ? "Favourite" : "Add to favourites"}
      </button>
      <button class="btn btn-outline-danger" onclick={deleteRecipe}>
        <i class="bi bi-trash"></i>
      </button>
    </div>

    <h5>Lists</h5>
    <div class="d-flex flex-wrap gap-1 mb-2">
      {#each currentLists as l}
        <span class="filter-pill">
          {l.name}
          <button
            class="btn btn-sm btn-link p-0"
            onclick={() => removeFromList(l.id)}
            aria-label="Remove"
          >
            ×
          </button>
        </span>
      {/each}
    </div>
    {#if availableLists.length > 0}
      <div class="dropdown mb-2">
        <button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
          Add to list
        </button>
        <ul class="dropdown-menu">
          {#each availableLists as l}
            <li>
              <button class="dropdown-item" onclick={() => addToList(l.id)}>
                {l.name}
              </button>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
    <form
      class="d-flex gap-1 mb-3"
      onsubmit={(e) => { e.preventDefault(); createListAndAdd(); }}
    >
      <input
        class="form-control form-control-sm"
        type="text"
        bind:value={newListName}
        placeholder="New list name"
      />
      <button class="btn btn-sm btn-primary" type="submit" disabled={busy}>
        Create + add
      </button>
    </form>

    <h5>Keywords</h5>
    {#if editingKeywords}
      <textarea class="form-control mb-2" rows="2" bind:value={keywordsInput}></textarea>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-primary" disabled={busy} onclick={saveKeywords}>
          Save
        </button>
        <button class="btn btn-sm btn-outline-secondary" onclick={() => (editingKeywords = false)}>
          Cancel
        </button>
      </div>
    {:else}
      <div class="mb-2">
        {#each recipe.keywords as k}
          <span class="filter-pill me-1 mb-1">{k}</span>
        {:else}
          <span class="text-secondary small">No keywords</span>
        {/each}
      </div>
      <button class="btn btn-sm btn-outline-secondary" onclick={() => (editingKeywords = true)}>
        Edit keywords
      </button>
    {/if}
  </div>

  <div class="col-md-7">
    <h1 class="h2">{recipe.clean_name}</h1>
    <p class="text-secondary">
      from <a href={`/books/${recipe.book_id}`}>{recipe.book_clean_title}</a>
      by {recipe.book_author}
    </p>
    {#if recipe.description}
      <p>{recipe.description}</p>
    {/if}
    {#if recipe.yields}
      <p class="text-secondary"><strong>Yields:</strong> {recipe.yields}</p>
    {/if}

    <h2 class="h5 mt-4">Ingredients</h2>
    <ul>
      {#each recipe.ingredients as ing}
        <li>{ing}</li>
      {/each}
    </ul>

    <h2 class="h5 mt-4">Instructions</h2>
    <ol>
      {#each recipe.instructions as step}
        <li class="mb-2">{step}</li>
      {/each}
    </ol>
  </div>
</article>
