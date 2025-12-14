import string
import uuid
from pathlib import Path
from typing import Optional

from django.db import models
from pydantic import BaseModel as PydanticBase
from pydantic import Field


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        abstract = True


class Book(BaseModel):
    calibre_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=500)
    pubdate = models.DateField(null=True, blank=True)
    calibre_added_at = models.DateTimeField(null=True, blank=True)
    path = models.CharField(max_length=1000)
    isbn = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)

    def get_epub_path(self) -> Path:
        book_path = Path(self.path)
        epub_files = list(book_path.glob("*.epub"))
        return epub_files[0]

    def get_cover_image_path(self) -> Path:
        return Path(self.path) / 'cover.jpg'

    def get_cookmarks_dir(self) -> Path:
        cookmarks_dir = Path(self.path) / '_cookmarks'
        cookmarks_dir.mkdir(exist_ok=True)
        return cookmarks_dir

    def get_recipes_json_path(self) -> Path:
        return self.get_cookmarks_dir() / 'recipes.json'

    def get_log_path(self) -> Path:
        return self.get_cookmarks_dir() / 'extraction.log'

    def get_report_path(self) -> Path:
        return self.get_cookmarks_dir() / 'report.json'

    @property
    def clean_title(self) -> str:
        return self.title.split(':')[0].strip()

    def __str__(self):
        return f"{self.author} - {self.title}"

    class Meta:
        ordering = ['author']


class ExtractionReport(BaseModel):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='extraction_reports')
    provider_name = models.CharField(max_length=50, null=True)
    model_name = models.CharField(max_length=200, null=True)
    queued_at = models.DateTimeField(auto_now_add=True, null=False)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    total_chapters = models.PositiveIntegerField(default=0)
    chapters_processed = models.JSONField(default=list)
    extraction_method = models.CharField(
        max_length=50,
        null=True,
        choices=[('file', 'File'), ('block', 'Block')],
    )
    images_in_separate_chapters = models.BooleanField(null=True)
    images_can_be_matched = models.BooleanField(null=True)
    recipes_found = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.book.title} - {self.started_at}"

    class Meta:
        ordering = ['-started_at']


class Keyword(BaseModel):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Recipe(BaseModel):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='recipes')
    extraction_report = models.ForeignKey(ExtractionReport, on_delete=models.SET_NULL, related_name='recipes', null=True, blank=True)
    order = models.PositiveIntegerField()
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    ingredients = models.JSONField(null=True)
    instructions = models.JSONField(null=True)
    yields = models.CharField(max_length=200, blank=True, null=True)
    image = models.TextField(blank=True, null=True)
    keywords = models.ManyToManyField(Keyword, related_name='recipes', blank=True)

    def __str__(self):
        return f"{self.name} ({self.book.author} - {self.book.title})"

    def get_next_in_book(self):
        return Recipe.objects.filter(book=self.book, order__gt=self.order).order_by('order').first()

    def get_previous_in_book(self):
        return Recipe.objects.filter(book=self.book, order__lt=self.order).order_by('-order').first()

    def to_recipe_data(self) -> 'RecipeData':
        return RecipeData(
            name=self.name,
            description=self.description,
            recipeIngredients=self.ingredients,
            recipeInstructions=self.instructions,
            recipeYield=self.yields,
            image=self.image,
            keywords=[keyword.name for keyword in self.keywords.all()],
            author=self.book.author,
            bookTitle=self.book.title,
            bookOrder=self.order,
        )

    class Meta:
        ordering = ['book', 'order']


class RecipeList(BaseModel):
    name = models.CharField(max_length=200)
    recipes = models.ManyToManyField(Recipe, through='RecipeListItem', related_name='recipe_lists', blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class RecipeListItem(BaseModel):
    recipe_list = models.ForeignKey(RecipeList, on_delete=models.CASCADE, related_name='items')
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='list_items')

    def __str__(self):
        return f"{self.recipe.name} in {self.recipe_list.name}"

    class Meta:
        ordering = ['-created_at']
        unique_together = ['recipe_list', 'recipe']


class RecipeData(PydanticBase):
    name: str
    description: Optional[str] = None
    ingredients: list[str] = Field(min_length=1, alias='recipeIngredients')
    instructions: list[str] = Field(min_length=1, alias='recipeInstructions')
    yields: Optional[str] = Field(None, alias='recipeYield')
    image: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    author: Optional[str] = None
    book_title: Optional[str] = Field(None, alias='bookTitle')
    book_order: Optional[int] = Field(None, alias='bookOrder')

    class Config:
        populate_by_name = True

    def model_post_init(self, __context):
        self.name = string.capwords(self.name)
        if self.yields:
            self.yields = (
                self.yields.capitalize()
                if self.yields[0].isalpha()
                else self.yields.lower()
            )


class Config(models.Model):
    AI_PROVIDER_CHOICES = [
        ('GEMINI', 'Google Gemini'),
        ('OPENROUTER', 'OpenRouter'),
    ]

    ai_provider = models.CharField(max_length=20, choices=AI_PROVIDER_CHOICES, blank=True)
    api_key = models.CharField(max_length=200, blank=True)
    extraction_rate_limit_per_minute = models.PositiveIntegerField(default=256)

    class Meta:
        verbose_name = 'Configuration'
        verbose_name_plural = 'Configuration'

    def __str__(self):
        return 'App Configuration'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def is_configured(cls):
        try:
            config = cls.objects.get(pk=1)
            return bool(config.ai_provider and config.api_key)
        except cls.DoesNotExist:
            return False
