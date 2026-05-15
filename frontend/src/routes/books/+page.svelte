<script lang="ts">
  import { books as booksApi } from "$api";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";

  let { data } = $props();

  let search = $state(data.filters.search);
  let sort = $state(data.filters.sort);
  let hasRecipes = $state(data.filters.has_recipes);
  let selectedAuthors = $state<string[]>([...data.filters.selected_authors]);
  let authorSearch = $state("");

  const filteredAuthors = $derived(
    authorSearch
      ? data.authors.filter((a) =>
          a.toLowerCase().includes(authorSearch.toLowerCase()),
        )
      : data.authors,
  );

  function apply() {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (sort) params.set("sort", sort);
    if (hasRecipes) params.set("has_recipes", "1");
    for (const a of selectedAuthors) params.append("selected_authors", a);
    goto(`/books?${params.toString()}`);
  }

  function gotoPage(n: number) {
    const params = new URLSearchParams(page.url.searchParams);
    params.set("page", String(n));
    goto(`/books?${params.toString()}`);
  }
</script>

<div class="row g-4">
  <aside class="col-lg-3 sidebar">
    <form onsubmit={(e) => { e.preventDefault(); apply(); }}>
      <div class="mb-3">
        <label class="form-label">Search</label>
        <input class="form-control" type="text" bind:value={search} />
      </div>
      <div class="form-check mb-3">
        <input
          id="has_recipes"
          class="form-check-input"
          type="checkbox"
          bind:checked={hasRecipes}
        />
        <label class="form-check-label" for="has_recipes">
          Only books with recipes
        </label>
      </div>
      <div class="mb-3">
        <label class="form-label">Sort</label>
        <select class="form-select" bind:value={sort}>
          <option value="random">Random</option>
          <option value="title">Title</option>
          <option value="author">Author</option>
          <option value="recipes">Most recipes</option>
          <option value="recent">Recently added</option>
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Authors ({data.authors.length})</label>
        <input
          class="form-control form-control-sm mb-2"
          type="text"
          bind:value={authorSearch}
          placeholder="Filter list..."
        />
        <select
          class="form-select"
          multiple
          size="10"
          bind:value={selectedAuthors}
        >
          {#each filteredAuthors as a}
            <option value={a}>{a}</option>
          {/each}
        </select>
      </div>
      <button class="btn btn-primary w-100" type="submit">Apply</button>
    </form>
  </aside>

  <section class="col-lg-9">
    <header class="d-flex justify-content-between align-items-baseline mb-3">
      <h1 class="h4 mb-0">Books</h1>
      <span class="text-secondary">{data.list.total} total</span>
    </header>

    <div class="row row-cols-2 row-cols-md-3 row-cols-xl-4 g-3">
      {#each data.list.items as b}
        <div class="col">
          <a href={`/books/${b.id}`} class="book-card">
            <img
              src={booksApi.coverUrl(b.id)}
              alt={b.title}
              class="cover mb-2"
              loading="lazy"
            />
            <div class="book-card-title small fw-semibold">{b.clean_title}</div>
            <div class="text-secondary small">{b.author}</div>
            {#if b.recipe_count > 0}
              <div class="text-success small mt-1">
                <i class="bi bi-journal-text"></i>
                {b.recipe_count} recipe{b.recipe_count === 1 ? "" : "s"}
              </div>
            {/if}
          </a>
        </div>
      {/each}
    </div>

    {#if data.list.pages > 1}
      <nav class="d-flex justify-content-center mt-4">
        <ul class="pagination">
          <li class="page-item" class:disabled={!data.list.has_previous}>
            <button
              class="page-link"
              onclick={() => gotoPage(data.list.page - 1)}
            >
              Previous
            </button>
          </li>
          <li class="page-item disabled">
            <span class="page-link">
              {data.list.page} of {data.list.pages}
            </span>
          </li>
          <li class="page-item" class:disabled={!data.list.has_next}>
            <button
              class="page-link"
              onclick={() => gotoPage(data.list.page + 1)}
            >
              Next
            </button>
          </li>
        </ul>
      </nav>
    {/if}
  </section>
</div>
