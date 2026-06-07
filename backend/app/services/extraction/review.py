"""The single human-in-the-loop decision in extraction.

When a file-method run finds zero images, the graph pauses and asks the operator
whether the cookbook actually has photos. The question text, the choices offered, and
the answers accepted are defined here once and shared by the three places that must
agree: the graph (which raises the interrupt), the resume path (which validates the
answer), and the read schema (which surfaces the pending question to the UI).
"""

REVIEW_QUESTION = "Zero images found. Does this cookbook have photos?"

# (value, label): value is the resume token the graph expects; label is what the
# operator sees on the choice. Order is the order the choices are presented in.
REVIEW_CHOICES: tuple[tuple[str, str], ...] = (
    ("has_images", "Yes, it has photos"),
    ("no_images", "No photos"),
)

VALID_HUMAN_RESPONSES: frozenset[str] = frozenset(value for value, _label in REVIEW_CHOICES)
