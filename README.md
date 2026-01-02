# cookmarks

A Django app for extracting, browsing and organising recipes from digital cookbooks in the EPUB format.

I have a Calibre library with hundreds of EPUB cookbooks, and I got tired of never being able to find that one recipe I vaguely remembered and having to use certain devices to read them. This app uses LLMs to extract the recipes into a structured format and store them into a searchable database so I can actually find and use them.

![Recipe](docs/recipe.png)


## Stack

- Python/Django
- SQLite
- LangGraph for agentic workflows
- HTMX for the interactive bits
- Bootstrap 5 (greyscale minimal aesthetic)
- Works with Gemini or OpenRouter APIs

## How it works

### Calibre integration

The app connects to your Calibre database and syncs metadata for books tagged 'Food' that have epub format. Title, author, publication date, ISBN, description, path on disk.

### Recipe extraction

This is the interesting part. Cookbook layouts are inconsistent, so I implemented an agentic workflow using **LangGraph** to handle the extraction intelligently.

The app analyses the book to determine the best extraction strategy:

**Blocks of files** (High Context) - Books where recipes are scattered across chapters or have images in separate files requiring a larger context window (128k) to associate text with images correctly.

**Single files** (Low Context) - Books where each recipe lives in its own file (common in modern epubs). Simple, fast, and cheap.

**Agentic decision making** - If the initial extraction yields recipes but no images, the workflow pauses and asks for human intervention via the UI: "Does this book actually have images?". Depending on your answer, it recursively tries a different strategy or proceeds without them.

The workflow:

```text
          [analyse_epub]
           /          \
      (File mode)    (Block mode)
          |               |
    [extract_file]   [extract_block] <----+
          \               /               |
           \             /          (User: "Has images")
            -> [validate]                 |
              /          \                |
        (Has images?)  (No images?)       |
            |              |              |
            |        [await_human] -------+
            |              |
            |        (User: "No images")
            |              |
            v              v
           [resolve_images]
                  |
              [finalise]
```

The process:
1. **Analyse**: Check file structure and sample content to pick a strategy.
2. **Extract**: Send content to the LLM with a schema.
3. **Validate**: Check if we got what we expected (particularly regarding images).
4. **Human in the Loop**: If results are ambiguous, pause and ask the user.
5. **Resolve**: Match extracted image paths to actual files in the epub archive.
6. **Finalise**: Save structured data to the database.

Each recipe stores: name, description, author, book link, ingredients, instructions, yields, image, and keywords.

### The frontend

**Books** - Grid of book covers. Filter by author, search by title. Toggle grid/list view. Sorted by when they were added to Calibre.

**Book detail** - Cover, metadata, description. Queue extraction, clear images, update metadata, delete.

**Recipes** - All recipes with filtering by keyword, book, author, list, or search query. Search works across title, ingredients, instructions, keywords, author, and book. Multiselect for bulk adding to lists. Pagination that respects your filters.

**Recipe detail** - Clean layout with image and ingredients/instructions. Breadcrumb navigation showing your context (book, list, or search results). Prev/next arrows navigate within that context. Keyboard shortcut 's' toggles favourite. Actions for lists, keywords, admin edit, clear image, delete.

**Lists** - Organise recipes into collections. There's a default Favourites list that's always there.

**Extraction reports** - History of all extraction attempts with stats: book, method, model, timestamp, recipes found, cost, tokens. Useful for debugging and tracking API usage.

## Configuration

There's a Config singleton that stores:
- AI provider (Gemini or OpenRouter)
- API key
- Extraction rate limit per minute

The app won't let you extract recipes until this is configured.

## Running it

### With Docker Compose

Uses supervisor to run gunicorn and django-q for async extraction jobs.

```
services:
  cookmarks:
    image: cookmarks:latest
    ports:
      - "8789:8789"
    volumes:
      - ./data:/data # holds app sqlite db
      - <path to calibre library>:/books # holds calibre library
    restart: unless-stopped
```
