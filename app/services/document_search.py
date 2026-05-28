import logging
import re
from functools import lru_cache

from elasticsearch import BadRequestError, NotFoundError

from app.config import ELASTICSEARCH_URL, INDEX_NAME, es

logger = logging.getLogger("app.services.document_search")

WILDCARD_SPECIALS = re.compile(r"([*?\\])")


@lru_cache(maxsize=1)
def _resolve_collapse_field() -> str:
    """
    Tentukan field collapse berdasarkan mapping aktual index.
    - Jika document_id sudah bertipe 'keyword' (mis. di ES Cloud kita), pakai langsung.
    - Jika 'text' dengan subfield '.keyword' (auto-mapping default), pakai 'document_id.keyword'.
    Fallback ke 'document_id' agar tidak menggagalkan request kalau mapping tak terbaca.
    """
    try:
        mapping = es.indices.get_mapping(index=INDEX_NAME)
    except NotFoundError:
        return "document_id"
    except Exception as exc:
        logger.warning("Tidak bisa membaca mapping %s: %s", INDEX_NAME, exc)
        return "document_id"

    try:
        props = mapping[INDEX_NAME]["mappings"]["properties"]
        node = props.get("document_id", {})
        if node.get("type") == "keyword":
            return "document_id"
        if "fields" in node and node["fields"].get("keyword", {}).get("type") == "keyword":
            return "document_id.keyword"
    except KeyError:
        pass
    return "document_id"


class ElasticsearchConnectionError(Exception):
    """Raised when the Elasticsearch cluster is unreachable before search."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ElasticsearchSearchError(Exception):
    """Raised when Elasticsearch rejects or fails the search request."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _ensure_elasticsearch_connection() -> None:
    try:
        if not es.ping():
            raise ElasticsearchConnectionError(
                f"Cannot connect to Elasticsearch at {ELASTICSEARCH_URL}: "
                "cluster did not respond to ping."
            )
    except ElasticsearchConnectionError:
        raise
    except Exception as e:
        raise ElasticsearchConnectionError(
            f"Cannot connect to Elasticsearch at {ELASTICSEARCH_URL}: {e}"
        ) from e


def _parse_search_input(raw: str) -> tuple[str, bool]:
    """
    Returns (search_text, is_phrase_mode).
    Phrase mode when entire string is wrapped in "..." or '...'.
    """
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        inner = text[1:-1].strip()
        if not inner:
            raise ValueError("Search query must not be empty.")
        return inner, True
    if not text:
        raise ValueError("Search query must not be empty.")
    return text, False


def _sanitize_wildcard_text(text: str) -> str:
    """Escape *, ?, \\ so user input does not break wildcard syntax."""
    return WILDCARD_SPECIALS.sub(r"\\\1", text)


def _filename_wildcard_phrase(search_text: str) -> str:
    """Quoted mode: *super strong*"""
    inner = " ".join(_sanitize_wildcard_text(search_text).lower().split())
    return f"*{inner}*"


def _filename_wildcard_terms(search_text: str) -> str:
    """Unquoted mode: *super*strong*"""
    terms = [
        _sanitize_wildcard_text(t).lower()
        for t in search_text.split()
        if t.strip()
    ]
    if not terms:
        raise ValueError("Search query must not be empty.")
    return "*" + "*".join(terms) + "*"


def _build_phrase_query(search_text: str) -> dict:
    return {
        "bool": {
            "should": [
                {
                    "match_phrase_prefix": {
                        "content": {"query": search_text, "boost": 3},
                    }
                },
                {
                    "wildcard": {
                        "filename": {
                            "value": _filename_wildcard_phrase(search_text),
                            "case_insensitive": True,
                            "boost": 6,
                        }
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def _build_flexible_query(search_text: str) -> dict:
    return {
        "bool": {
            "should": [
                {
                    "match": {
                        "content": {
                            "query": search_text,
                            "operator": "and",
                            "boost": 1.5,
                        }
                    }
                },
                {
                    "wildcard": {
                        "filename": {
                            "value": _filename_wildcard_terms(search_text),
                            "case_insensitive": True,
                            "boost": 5,
                        }
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def _build_search_query(raw: str) -> tuple[dict, str, bool]:
    """Returns (es_query_body, search_text, is_phrase_mode)."""
    search_text, is_phrase = _parse_search_input(raw)
    if is_phrase:
        return _build_phrase_query(search_text), search_text, True
    return _build_flexible_query(search_text), search_text, False


def search_documents(
    query: str,
    *,
    size: int = 20,
    from_: int = 0,
) -> dict:
    """
    Full-text search on indexed pages; collapse by document_id so one hit per document.
    """
    size = min(max(size, 1), 100)
    from_ = max(from_, 0)

    _ensure_elasticsearch_connection()

    es_query, search_text, is_phrase = _build_search_query(query)
    # Collapse harus pakai field bertipe keyword.
    # Resolve otomatis sesuai mapping aktual (ES Cloud vs auto-mapping lokal).
    collapse_field = _resolve_collapse_field()

    search_kwargs: dict = {
        "index": INDEX_NAME,
        "query": es_query,
        "collapse": {"field": collapse_field},
        "from_": from_,
        "size": size,
        "highlight": {
            "fields": {
                "content": {
                    "fragment_size": 200,
                    "number_of_fragments": 1,
                }
            }
        },
        "sort": ["_score"],
    }

    logger.info(
        "Search search_text=%r mode=%s collapse_field=%s",
        search_text,
        "phrase" if is_phrase else "flexible",
        collapse_field,
    )

    try:
        response = es.search(**search_kwargs)
    except BadRequestError as e:
        raise ElasticsearchSearchError(
            f"Elasticsearch search failed: {e.message}"
        ) from e

    hits = response.get("hits", {})
    total_raw = hits.get("total", 0)
    total_pages = total_raw["value"] if isinstance(total_raw, dict) else int(total_raw)

    documents = []
    for hit in hits.get("hits", []):
        source = hit.get("_source", {})
        item = {
            "document_id": source.get("document_id"),
            "filename": source.get("filename"),
            "publish_date": source.get("publish_date"),
            "page_number": source.get("page_number"),
            "score": hit.get("_score"),
        }
        highlight = hit.get("highlight", {})
        if highlight.get("content"):
            item["content_snippet"] = highlight["content"][0]
        else:
            content = source.get("content") or ""
            item["content_snippet"] = content[:300] + ("..." if len(content) > 300 else "")

        documents.append(item)

    logger.info(
        "Search search_text=%r mode=%s collapsed_results=%s total_pages_matched=%s",
        search_text,
        "phrase" if is_phrase else "flexible",
        len(documents),
        total_pages,
    )

    return {
        "query": search_text,
        "search_mode": "phrase" if is_phrase else "flexible",
        "total_pages_matched": total_pages,
        "total_documents": len(documents),
        "documents": documents,
    }
