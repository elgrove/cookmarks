<script lang="ts">
  import { books as booksApi } from "$api";
  let { data } = $props();
  const home = $derived(data.home);
</script>

<div class="container py-4">
  <div class="text-center mb-5">
    <h1 class="display-4 fw-bold">cookmarks</h1>
    <p class="lead text-secondary">
      AI-extracted recipes from your digital cookbook library
    </p>
  </div>

  {#if !home.is_configured}
    <div class="alert alert-warning d-flex align-items-center gap-2">
      <i class="bi bi-exclamation-triangle"></i>
      <div>
        Set your AI provider and API key on the
        <a href="/config" class="alert-link">Config page</a>
        to enable extraction.
      </div>
    </div>
  {/if}

  <div class="row g-4 mb-5">
    <div class="col-md-4">
      <a href="/books" class="d-block p-4 border rounded text-decoration-none text-body h-100">
        <i class="bi bi-book fs-2 d-block mb-2"></i>
        <h5 class="mb-1">{home.books_count} books</h5>
        <span class="text-secondary">Browse your library</span>
      </a>
    </div>
    <div class="col-md-4">
      <a href="/recipes" class="d-block p-4 border rounded text-decoration-none text-body h-100">
        <i class="bi bi-journal-richtext fs-2 d-block mb-2"></i>
        <h5 class="mb-1">Recipes</h5>
        <span class="text-secondary">{home.has_recipes ? "Search and explore" : "Extract from a book to begin"}</span>
      </a>
    </div>
    <div class="col-md-4">
      <a href="/tasks" class="d-block p-4 border rounded text-decoration-none text-body h-100">
        <i class="bi bi-cpu fs-2 d-block mb-2"></i>
        <h5 class="mb-1">Tasks</h5>
        <span class="text-secondary">Run background jobs</span>
      </a>
    </div>
  </div>

  {#if home.book_of_the_day}
    {@const b = home.book_of_the_day}
    <h2 class="h5 text-uppercase text-secondary mb-3">Book of the day</h2>
    <a href={`/books/${b.id}`} class="book-card row g-4">
      <div class="col-md-3">
        <img src={booksApi.coverUrl(b.id)} alt={b.title} class="cover" />
      </div>
      <div class="col-md-9">
        <h3 class="book-card-title">{b.clean_title}</h3>
        <p class="text-secondary mb-2">{b.author}</p>
        {#if b.description}
          <div class="text-body-secondary">
            {@html b.description}
          </div>
        {/if}
      </div>
    </a>
  {/if}
</div>
