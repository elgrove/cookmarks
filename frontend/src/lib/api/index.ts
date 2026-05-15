import { apiFetch, type FetchOptions } from "./client";
import type {
  AISearchResult,
  AuthConfig,
  Book,
  BookDetail,
  Config,
  ExtractionReportsBundle,
  HomeStats,
  Keyword,
  Paginated,
  RecipeDetail,
  RecipeListSummary,
  RecipeSummary,
  TasksOverview,
  User,
} from "./types";

type FetchArg = { fetch?: typeof fetch };

export const auth = {
  me: (opts?: FetchArg) =>
    apiFetch<User>("/auth/me", { fetch: opts?.fetch }),
  config: (opts?: FetchArg) =>
    apiFetch<AuthConfig>("/auth/config", { fetch: opts?.fetch }),
  login: (username: string, password: string, opts?: FetchArg) =>
    apiFetch<User>("/auth/login", {
      method: "POST",
      body: { username, password },
      fetch: opts?.fetch,
    }),
  logout: (opts?: FetchArg) =>
    apiFetch<{ detail: string }>("/auth/logout", {
      method: "POST",
      fetch: opts?.fetch,
    }),
};

export const stats = {
  home: (opts?: FetchArg) =>
    apiFetch<HomeStats>("/stats/home", { fetch: opts?.fetch }),
};

export const books = {
  list: (
    params: {
      search?: string;
      selected_authors?: string[];
      has_recipes?: boolean;
      sort?: string;
      page?: number;
      page_size?: number;
    } = {},
    opts?: FetchArg,
  ) =>
    apiFetch<Paginated<Book>>("/books", {
      query: params as FetchOptions["query"],
      fetch: opts?.fetch,
    }),
  authors: (opts?: FetchArg) =>
    apiFetch<string[]>("/books/authors", { fetch: opts?.fetch }),
  get: (id: string, opts?: FetchArg) =>
    apiFetch<BookDetail>(`/books/${id}`, { fetch: opts?.fetch }),
  remove: (id: string) =>
    apiFetch<{ detail: string }>(`/books/${id}`, { method: "DELETE" }),
  extract: (id: string, body: { extraction_method?: string; model_name?: string } = {}) =>
    apiFetch<{ detail: string }>(`/books/${id}/extract`, {
      method: "POST",
      body,
    }),
  clearImages: (id: string) =>
    apiFetch<{ detail: string }>(`/books/${id}/clear-images`, {
      method: "POST",
    }),
  clearRecipes: (id: string) =>
    apiFetch<{ detail: string }>(`/books/${id}/clear-recipes`, {
      method: "POST",
    }),
  generateEmbeddings: (id: string) =>
    apiFetch<{ detail: string }>(`/books/${id}/generate-embeddings`, {
      method: "POST",
    }),
  coverUrl: (id: string) => `/api/v1/books/${id}/cover`,
};

export const recipes = {
  list: (
    params: Record<string, string | number | boolean | string[] | undefined> = {},
    opts?: FetchArg,
  ) =>
    apiFetch<Paginated<RecipeSummary>>("/recipes", {
      query: params,
      fetch: opts?.fetch,
    }),
  get: (
    id: string,
    params: Record<string, string | number | string[] | undefined> = {},
    opts?: FetchArg,
  ) =>
    apiFetch<RecipeDetail>(`/recipes/${id}`, {
      query: params,
      fetch: opts?.fetch,
    }),
  remove: (id: string) =>
    apiFetch<{ detail: string }>(`/recipes/${id}`, { method: "DELETE" }),
  clearImage: (id: string) =>
    apiFetch<{ detail: string }>(`/recipes/${id}/clear-image`, {
      method: "POST",
    }),
  setKeywords: (id: string, keywords: string[]) =>
    apiFetch<{ detail: string }>(`/recipes/${id}/keywords`, {
      method: "PUT",
      body: { keywords },
    }),
  toggleFavourite: (id: string) =>
    apiFetch<{ is_favourite: boolean }>(`/recipes/${id}/toggle-favourite`, {
      method: "POST",
    }),
  similar: (id: string, opts?: FetchArg) =>
    apiFetch<RecipeSummary[]>(`/recipes/${id}/similar`, { fetch: opts?.fetch }),
  aiSearch: (prompt: string, limit = 1000) =>
    apiFetch<AISearchResult>("/recipes/ai-search", {
      method: "POST",
      body: { prompt, limit },
    }),
  imageUrl: (bookId: string, imagePath: string) =>
    `/api/v1/recipes/image/${bookId}/${imagePath}`,
};

export const lists = {
  list: (opts?: FetchArg) =>
    apiFetch<RecipeListSummary[]>("/lists", { fetch: opts?.fetch }),
  favourites: (opts?: FetchArg) =>
    apiFetch<RecipeListSummary>("/lists/favourites", { fetch: opts?.fetch }),
  get: (id: string, opts?: FetchArg) =>
    apiFetch<RecipeListSummary>(`/lists/${id}`, { fetch: opts?.fetch }),
  create: (name: string) =>
    apiFetch<RecipeListSummary>("/lists", {
      method: "POST",
      body: { name },
    }),
  remove: (id: string) =>
    apiFetch<{ detail: string }>(`/lists/${id}`, { method: "DELETE" }),
  addRecipe: (listId: string, recipeId: string) =>
    apiFetch<{ detail: string }>(`/lists/${listId}/recipes/${recipeId}`, {
      method: "POST",
    }),
  removeRecipe: (listId: string, recipeId: string) =>
    apiFetch<{ detail: string }>(`/lists/${listId}/recipes/${recipeId}`, {
      method: "DELETE",
    }),
};

export const keywords = {
  list: (opts?: FetchArg) =>
    apiFetch<Keyword[]>("/keywords", { fetch: opts?.fetch }),
};

export const tasks = {
  overview: (opts?: FetchArg) =>
    apiFetch<TasksOverview>("/tasks", { fetch: opts?.fetch }),
  loadBooks: () =>
    apiFetch<{ detail: string }>("/tasks/load-books", { method: "POST" }),
  dedupeKeywords: () =>
    apiFetch<{ detail: string }>("/tasks/dedupe-keywords", { method: "POST" }),
  queueAllExtractions: (extraction_method?: string) =>
    apiFetch<{ detail: string }>("/tasks/queue-all-extractions", {
      method: "POST",
      body: { extraction_method },
    }),
  queueRandomExtractions: (count: number, extraction_method?: string) =>
    apiFetch<{ detail: string }>("/tasks/queue-random-extractions", {
      method: "POST",
      body: { count, extraction_method },
    }),
};

export const config = {
  get: (opts?: FetchArg) =>
    apiFetch<Config>("/config", { fetch: opts?.fetch }),
  update: (body: Partial<{ ai_provider: string; api_key: string; extraction_rate_limit_per_minute: number }>) =>
    apiFetch<Config>("/config", { method: "PATCH", body }),
};

export const extraction = {
  reports: (opts?: FetchArg) =>
    apiFetch<ExtractionReportsBundle>("/extraction-reports", {
      fetch: opts?.fetch,
    }),
  resume: (reportId: string, response: "has_images" | "no_images") =>
    apiFetch<{ detail: string }>(`/extraction-reports/${reportId}/resume`, {
      method: "POST",
      body: { response },
    }),
};

export type { User, AuthConfig, Book, BookDetail, Keyword, RecipeSummary, RecipeDetail, RecipeListSummary, Paginated, Config, ExtractionReportsBundle, AISearchResult, HomeStats, TasksOverview };
