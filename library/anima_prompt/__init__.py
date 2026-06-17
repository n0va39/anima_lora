"""ANIMA prompt/caption correction helpers.

This package is intentionally dependency-light. It does not import torch,
ComfyUI, model code, or taggers, so the same core can be reused by CLI tools
and future UI nodes.
"""

from .animadex import (
    AnimaDexArtist,
    AnimaDexCharacter,
    AnimaDexDB,
    AnimaDexImportClient,
    AnimaDexImportError,
    AnimaDexImportToken,
    AnimaDexTokenStore,
)
from .correction import correct_prompt, inspect_prompt
from .knowledge import (
    GeneralTagDB,
    KnowledgeBaseNotFound,
    PromptKnowledgeBase,
    load_knowledge_base,
)
from .models import CorrectionResult, ParsedPrompt, TagInfo, TagToken

__all__ = [
    "AnimaDexArtist",
    "AnimaDexCharacter",
    "AnimaDexDB",
    "AnimaDexImportClient",
    "AnimaDexImportError",
    "AnimaDexImportToken",
    "AnimaDexTokenStore",
    "CorrectionResult",
    "GeneralTagDB",
    "KnowledgeBaseNotFound",
    "ParsedPrompt",
    "PromptKnowledgeBase",
    "TagInfo",
    "TagToken",
    "correct_prompt",
    "inspect_prompt",
    "load_knowledge_base",
]
