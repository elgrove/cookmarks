IMAGE_MATCH_CHECK_PROMPT = """Analyse this sample of HTML content from an EPUB cookbook.

The book contains recipes for dishes, some or all of the recipes may have an accompanying image.
The book may have images stored in separate chapter files, away from the recipe text, meaning we cannot rely on the image being in the same file as the clue to match the image to the recipe.
Your job is to look at the sample of several files and determine if it's possible to reliably match images to their corresponding recipes using nearby text, captions or any other clues in the HTML content.

Look for:
- <figcapgtion> tags describing an image with the name of the dish
- <img> tags with the name of the dish close by, especially if the image and the text are the only thing on the page
- Text near the image that identifies the dish
- File naming patterns that match between image chapters and recipe chapters
- Any other clues that would allow matching images to recipes


Examples of images with captions/indicators (result would be "yes")

1.
<p id="filepos104418" class="calibre_3"><span class="calibre3"><span class="bold">Fancy Citrusy Olives</span></span></p><blockquote class="calibre_19"><span class="calibre1">  </span><a></a><img src="images/00123.jpg" class="calibre_20"/><span class="calibre1">
2.
<figure class="image_full_caption"><img alt="" src="../images/p080.jpg"/>
<figcaption>SAMBAL FISH SAUCE WINGS WITH COOLING SPRING ONION DIP</figcaption>
3.
<img alt="" src="../image/p031.jpg"/>
<figcaption>
<p class="caption_1"><a href="p030.xhtml#eggs_two_ways">Eggs Two Ways</a></p>
</figcaption>
4.
<h1 class="chapter"><a id="page_126"/>JAPANESE CARBONARA</h1>
<p class="ser1"><a id="page_127"/><img alt="images" src="images/img-127-1.jpg"/></p>
5.
<p class="rec-ttl1" style="color:#ED1846;"><a id="pg96"/>LAMB SEEKH KEBABS</p>
<div class="ser"><a id="pg97"/><img alt="image" src="images/p97.jpg"/></div>
<p class="h3a" style="color:#ED1846;">SERVES 4 OR MORE AS PART OF A MULTI-COURSE MEAL</p>

Sample content:
{sample_content}

YOU MUST ONLY ANSWER WITH ONE WORD: yes OR no. LOWER CASE. NO PUNCTUATION. NO QUOTES. THIS IS ABSOLUTELY VITAL AND MUST BE ADHERED TO.
- "no" means there is no reliable way to match images to recipes, there is no text near to the image that gives any indication
- "yes" means images CAN be reliably matched to recipes, because text nearby contains the name of a dish that is in the image
"""

EXTRACT_RECIPES_PROMPT = """- Your job is to extract recipes from cookbook content, returning JSON in the provided schema
- A recipe is fundamentally a list of >=1 ingredients and a list of >=1 instructions to create the dish from those ingrendients
- Read the schema carefully to understand the shape and nature of the data to return
- Extract text verbatim, exactly as it appears in the book, do not rephrase or rewrite
- Not all recipes have an image but look for figcaption tags, nearby text labels or any other clues linking each recipe to an image. Provide the relative path as shown in the EPUB file structure (e.g. '../images/recipe.jpg' or 'images/p026.jpg').
- Some books use an image to define a bullet point or other icon, a tell for this is seeing it more than once in a chapter. We want to ignore these images.
- Always use UK English terms in the keywords, never use Americanisms, for example use 'starter' but never 'appetizer', 'grill' never 'broil', 'aubergine' never 'eggplant', 'mince' never 'ground meat', etc)
- Return only a valid JSON array of recipe objects
- If you cannot find a recipe meeting the definition above in the content, return empty array []
- Ignore recipes referred to in tables of contents or indexes

Recipes Schema:
{schema}

Cookbook Content:
{content}

Return ONLY a JSON array of recipe objects. No other text."""

DEDUPLICATE_KEYWORDS_PROMPT = """You are tasked with deduplicating a list of keywords. These are keywords/tags of recipes extracted from cookbooks.
Analyze the provided list and identify keywords that are variations of each other (e.g., different capitalization, pluralization, or hyphenation), or are very similar and serve the same purpose as tags/keywords.

Respond with a JSON object where:
- The keys are the duplicate keywords.
- The values are the single, canonical keyword to replace them with.

Choose the most common or sensible form as the canonical version. For example, if you have "Stir Fry", "Stir-Fry", and "stir-fry", you might choose "Stir-fry" as the canonical form.

Here is the list of keywords:
{keywords}

Return ONLY a valid JSON object. No other text.
"""
