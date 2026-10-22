import hashlib

# Bump when the chunking algorithm or the embedded text format changes,
# so every stored document is reprocessed.
CHUNKER_VERSION = "md-header+recursive@v1"


def sig(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def content_hash(normalized_markdown: str) -> str:
    return sig(normalized_markdown)


def chunker_descriptor(*, size: int, overlap: int, min_size: int) -> str:
    # breadcrumb=1: the heading path is prepended to the text that gets embedded.
    return f"{CHUNKER_VERSION}/size={size}/overlap={overlap}/min={min_size}/breadcrumb=1"


def embedder_descriptor(*, model: str, dimensions: int) -> str:
    return f"{model}/document/{dimensions}"


def chunk_signature(content_hash: str, chunker: str) -> str:
    return sig(content_hash, chunker)


def embed_signature(chunk_signature: str, embedder: str) -> str:
    return sig(chunk_signature, embedder)


def make_doc_id(tenant: str, source_key: str) -> str:
    return "upload-" + hashlib.sha256(f"{tenant}:upload:{source_key}".encode()).hexdigest()[:12]
