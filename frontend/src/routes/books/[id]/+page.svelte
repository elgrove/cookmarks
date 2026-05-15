<script lang="ts">
  import { books as booksApi } from "$api";
  import { goto } from "$app/navigation";
  import RecipeCard from "$components/RecipeCard.svelte";

  let { data } = $props();
  const { book, sample } = data;

  let extractionMethod = $state<string>("");
  let modelName = $state<string>("");
  let busy = $state(false);
  let toast = $state<string | null>(null);

  function flash(msg: string) {
    toast = msg;
    setTimeout(() => (toast = null), 3000);
  }

  async function extract() {
    busy = true;
    try {
      const res = await booksApi.extract(book.id, {
        extraction_method: extractionMethod || undefined,
        model_name: modelName || undefined,
      });
      flash(res.detail);
    } finally {
      busy = false;
    }
  }

  async function clearImages() {
    if (!confirm("Remove all recipe images from this book?")) return;
    busy = true;
    try {
      flash((await booksApi.clearImages(book.id)).detail);
    } finally {
      busy = false;
    }
  }

  async function clearRecipes() {
    if (!confirm("Delete all recipes from this book?")) return;
    busy = true;
    try {
      flash((await booksApi.clearRecipes(book.id)).detail);
    } finally {
      busy = false;
    }
  }

  async function generateEmbeddings() {
    busy = true;
    try {
      flash((await booksApi.generateEmbeddings(book.id)).detail);
    } finally {
      busy = false;
    }
  }

  async function deleteBook() {
    if (!confirm(`Delete "${book.clean_title}" and all its recipes?`)) return;
    busy = true;
    try {
      await booksApi.remove(book.id);
      goto("/books");
    } finally {
      busy = false;
    }
  }
</script>

<nav aria-label="breadcrumb" class="mb-3">
  <ol class="breadcrumb mb-0">
    <li class="breadcrumb-item"><a href="/books">Books</a></li>
    <li class="breadcrumb-item active">{book.clean_title}</li>
  </ol>
</nav>

{#if toast}
  <div class="alert alert-info">{toast}</div>
{/if}

<div class="row g-4">
  <div class="col-md-3">
    <img src={booksApi.coverUrl(book.id)} alt={book.title} class="cover" />
  </div>
  <div class="col-md-9">
    <h1 class="h3">{book.clean_title}</h1>
    <p class="text-secondary">
      {book.author}{book.pubdate ? ` · ${book.pubdate}` : ""}
    </p>
    {#if book.description}
      <div class="text-body-secondary mb-3">{@html book.description}</div>
    {/if}

    <div class="d-flex flex-wrap gap-2 mb-3">
      <a href={`/recipes?book=${book.id}`} class="btn btn-outline-primary">
        <i class="bi bi-journal-text"></i>
        View all {book.recipe_count} recipes
      </a>
      {#if book.first_recipe_id}
        <a
          href={`/recipes/${book.first_recipe_id}?context=book`}
          class="btn btn-outline-secondary"
        >
          Read from first recipe
        </a>
      {/if}
    </div>

    <details class="mb-4">
      <summary class="h5">Actions</summary>
      <div class="border rounded p-3 mt-2">
        <div class="row g-2 mb-2">
          <div class="col-sm-4">
            <label class="form-label small">Extraction method</label>
            <select class="form-select form-select-sm" bind:value={extractionMethod}>
              <option value="">Auto</option>
              <option value="file">File</option>
              <option value="block">Block</option>
            </select>
          </div>
          {#if book.available_models.length}
            <div class="col-sm-6">
              <label class="form-label small">Model</label>
              <select class="form-select form-select-sm" bind:value={modelName}>
                <option value="">Default per step</option>
                {#each book.available_models as m}
                  <option value={m}>{m}</option>
                {/each}
              </select>
            </div>
          {/if}
        </div>
        <div class="d-flex flex-wrap gap-2">
          <button class="btn btn-sm btn-primary" disabled={busy} onclick={extract}>
            Queue extraction
          </button>
          <button
            class="btn btn-sm btn-outline-secondary"
            disabled={busy}
            onclick={generateEmbeddings}
          >
            Generate embeddings
          </button>
          <button
            class="btn btn-sm btn-outline-warning"
            disabled={busy}
            onclick={clearImages}
          >
            Clear images
          </button>
          <button
            class="btn btn-sm btn-outline-warning"
            disabled={busy}
            onclick={clearRecipes}
          >
            Clear recipes
          </button>
          <button class="btn btn-sm btn-outline-danger" disabled={busy} onclick={deleteBook}>
            Delete book
          </button>
        </div>
      </div>
    </details>
  </div>
</div>

{#if sample.length > 0}
  <h2 class="h5 mt-4 mb-3">Recipe sample</h2>
  <div class="row row-cols-2 row-cols-md-3 row-cols-xl-6 g-3">
    {#each sample as r}
      <div class="col">
        <RecipeCard recipe={r} contextParams={`context=book`} />
      </div>
    {/each}
  </div>
{/if}
