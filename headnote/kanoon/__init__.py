"""Indian Kanoon API client, HTML parser, and retrieval pipeline."""

from .client import (
    KanoonClient,
    KanoonError,
    KanoonAuthError,
    KanoonNotFound,
    KanoonRateLimited,
    KanoonServerError,
    KanoonBudgetExceeded,
    SearchHit,
    SearchPage,
    Document,
)
from .parser import ParsedJudgment, Paragraph, parse_judgment, extract_statutes
from .retrieval import (
    CaseSummary,
    RetrievalMeta,
    RetrievalResult,
    retrieve_for_situation,
    result_to_prompt_corpus_json,
    IK_PROMPT_ADDENDUM,
)

__all__ = [
    "KanoonClient", "KanoonError", "KanoonAuthError", "KanoonNotFound",
    "KanoonRateLimited", "KanoonServerError", "KanoonBudgetExceeded",
    "SearchHit", "SearchPage", "Document",
    "ParsedJudgment", "Paragraph", "parse_judgment", "extract_statutes",
    "CaseSummary", "RetrievalMeta", "RetrievalResult",
    "retrieve_for_situation", "result_to_prompt_corpus_json",
    "IK_PROMPT_ADDENDUM",
]
