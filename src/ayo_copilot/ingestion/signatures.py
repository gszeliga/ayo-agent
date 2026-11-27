import hashlib

from ayo_copilot.ingestion.chunking import SMALL_CHUNK_POLICY

# Bump when the chunking algorithm or the embedded text format changes,
# so every stored document is reprocessed.
CHUNKER_VERSION = "md-header+recursive@v3"


def sig(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def content_hash(normalized_markdown: str) -> str:
    return sig(normalized_markdown)


def chunker_descriptor(*, size: int, overlap: int, min_size: int) -> str:
    # breadcrumb=1: the heading path is prepended to the text that gets embedded.
    return (
        f"{CHUNKER_VERSION}/size={size}/overlap={overlap}/min={min_size}"
        f"/{SMALL_CHUNK_POLICY}/breadcrumb=1"
    )


def embedder_descriptor(*, provider: str, model: str, dimensions: int) -> str:
    """The vector space a document's vectors live in. The fake embedder's hash-derived
    vectors share no space with a real model's, so they are labelled `fake` whatever the
    model setting: a search or status check under the real provider then sees them as
    embedded with another config instead of mixing them in."""
    name = "fake" if provider == "fake" else model
    return f"{name}/document/{dimensions}"


def chunk_signature(content_hash: str, chunker: str) -> str:
    return sig(content_hash, chunker)


def embed_signature(chunk_signature: str, embedder: str) -> str:
    return sig(chunk_signature, embedder)


# Every id `make_doc_id` (or a future source type) produces: `<source type>-<12 hex>`.
DOC_ID_PATTERN = r"^[a-z]+-[0-9a-f]{12}$"


def make_doc_id(tenant: str, source_key: str) -> str:
    return "upload-" + hashlib.sha256(f"{tenant}:upload:{source_key}".encode()).hexdigest()[:12]
