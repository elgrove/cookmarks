export interface User {
  id: number;
  username: string;
  is_staff: boolean;
}

export interface AuthConfig {
  no_auth: boolean;
}

export interface Book {
  id: string;
  calibre_id: number;
  title: string;
  clean_title: string;
  author: string;
  pubdate: string | null;
  isbn: string;
  description: string;
  recipe_count: number;
}

export interface BookDetail extends Book {
  available_models: string[];
  sample_recipe_ids: string[];
  first_recipe_id: string | null;
}

export interface Keyword {
  id: string;
  name: string;
  recipe_count: number;
}

export interface RecipeSummary {
  id: string;
  book_id: string;
  book_title: string;
  book_clean_title: string;
  book_author: string;
  order: number;
  name: string;
  clean_name: string;
  description: string | null;
  yields: string | null;
  has_image: boolean;
  image: string | null;
  keywords: string[];
}

export interface NeighbourRecipe {
  id: string;
  name: string;
  clean_name: string;
}

export interface BreadcrumbContext {
  type: "book" | "list" | "search";
  book_id?: string | null;
  book_title?: string | null;
  list_id?: string | null;
  list_name?: string | null;
}

export interface RecipeDetail {
  id: string;
  book_id: string;
  book_title: string;
  book_clean_title: string;
  book_author: string;
  order: number;
  name: string;
  clean_name: string;
  description: string | null;
  yields: string | null;
  ingredients: string[];
  instructions: string[];
  image: string | null;
  keywords: string[];
  list_ids: string[];
  is_favourite: boolean;
  favourites_list_id: string;
  previous_recipe: NeighbourRecipe | null;
  next_recipe: NeighbourRecipe | null;
  breadcrumb: BreadcrumbContext | null;
}

export interface RecipeListSummary {
  id: string;
  name: string;
  is_default: boolean;
  recipe_count: number;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  pages: number;
  total: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface Config {
  ai_provider: string;
  api_key_masked: string;
  has_api_key: boolean;
  extraction_rate_limit_per_minute: number;
  is_configured: boolean;
}

export interface ExtractionReport {
  id: string;
  book_id: string;
  book_title: string;
  book_clean_title: string;
  book_author: string;
  provider_name: string | null;
  model_name: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  total_chapters: number;
  chapters_processed_count: number;
  extraction_method: string | null;
  images_in_separate_chapters: boolean | null;
  images_can_be_matched: boolean | null;
  recipes_found: number;
  cost_usd: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  status: string;
  image_count: number;
}

export interface ExtractionReportsBundle {
  reports: ExtractionReport[];
  total_books: number;
  total_recipes: number;
  processed_books: number;
  total_cost: number;
  provider_configured: boolean;
}

export interface AISearchResult {
  search_key: string;
  count: number;
}

export interface HomeStats {
  has_books: boolean;
  has_recipes: boolean;
  is_configured: boolean;
  books_count: number;
  book_of_the_day: Book | null;
}

export interface TasksOverview {
  books_count: number;
  books_with_recipes_count: number;
}
