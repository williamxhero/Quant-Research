"""UI-only internationalisation for the Manager GUI web shell.

Chinese (zh-CN, the default) and English share one `Translator` API. The language
is selected only by the `lang` URL parameter; the read-model API stays
language-neutral. Pages never import catalog modules directly: they ask a
`Translator` for a key.
"""

from .catalog import CATALOG, REGISTRY, CatalogError, CatalogRegistry, merge, register
from .glossary import TERMS, Term
from .locale import DEFAULT_LOCALE, LANG_PARAM, Locale, resolve_locale, with_lang
from .translator import (
    PSEUDO_CLOSE,
    PSEUDO_OPEN,
    M,
    TranslationError,
    Translator,
    source_text,
)

__all__ = [
    "CATALOG",
    "DEFAULT_LOCALE",
    "LANG_PARAM",
    "PSEUDO_CLOSE",
    "PSEUDO_OPEN",
    "REGISTRY",
    "TERMS",
    "CatalogError",
    "CatalogRegistry",
    "Locale",
    "M",
    "Term",
    "TranslationError",
    "Translator",
    "merge",
    "register",
    "resolve_locale",
    "source_text",
    "with_lang",
]
