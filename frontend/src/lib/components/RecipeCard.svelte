<script lang="ts">
  import type { RecipeSummary, RecipeDetail } from "$api/types";
  import { recipes as recipesApi } from "$api";

  interface Props {
    recipe: RecipeSummary | RecipeDetail;
    contextParams?: string;
  }

  let { recipe, contextParams = "" }: Props = $props();

  function imageSrc(r: Props["recipe"]): string | null {
    if (!r.image) return null;
    // image is either base64 data URI, or a path inside the EPUB
    if (r.image.startsWith("data:") || r.image.startsWith("http")) return r.image;
    return recipesApi.imageUrl(r.book_id, r.image);
  }

  const src = $derived(imageSrc(recipe));
  const href = $derived(
    `/recipes/${recipe.id}${contextParams ? `?${contextParams}` : ""}`,
  );
</script>

<a {href} class="recipe-card">
  {#if src}
    <img src={src} alt={recipe.name} class="recipe-card-img" loading="lazy" />
  {:else}
    <div class="recipe-card-img d-flex align-items-center justify-content-center text-secondary">
      <i class="bi bi-journal-text fs-3"></i>
    </div>
  {/if}
  <div class="recipe-card-body">
    <div class="recipe-card-title">{recipe.clean_name}</div>
    <div class="recipe-card-meta">
      {recipe.book_clean_title} · {recipe.book_author}
    </div>
  </div>
</a>
