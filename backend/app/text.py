import unicodedata

# Characters NFD leaves alone: they carry no combining accent to strip.
_SPECIALS = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ø": "o",
        "Ø": "o",
        "đ": "d",
        "Đ": "d",
        "ł": "l",
        "Ł": "l",
        "ß": "ss",
        "æ": "ae",
        "Æ": "ae",
        "œ": "oe",
        "Œ": "oe",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def fold(value: str | None) -> str:
    """Lower-case and strip accents, so a search for "souffle" finds "Soufflé"."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value.translate(_SPECIALS))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def stem(term: str) -> str:
    """Trim a plural ending so "tomatoes" also finds "tomato". Matching is by
    substring, so a shorter term only ever widens the result set."""
    if len(term) > 4 and term.endswith("es"):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term
