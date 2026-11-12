"""The retrieval query, built deterministically from the case state, not only the last
message.

Parts, in priority order: the problem statement (`what`, `where`), the latest user message,
the evidence (newest first) and the recorded hypotheses (newest first). Each part is
cleaned and put on one line; empty parts are skipped. The query is cut at
`QUERY_MAX_CHARS`, so what is lost first is the oldest hypotheses and evidence.
"""

from ayo_copilot.conversation.case import CaseSnapshot, clean_text

# The search service's own limit (`schemas.MAX_QUERY_CHARS`; a test keeps them equal).
QUERY_MAX_CHARS = 2000


def build_query(snapshot: CaseSnapshot, user_text: str) -> str:
    case = snapshot.case
    newest_first = list(reversed(snapshot.events))
    parts = [
        case.what,
        case.where_,
        user_text,
        *(e.content for e in newest_first if e.event_type == "evidence"),
        *(e.content for e in newest_first if e.event_type == "hypothesis"),
    ]
    lines = [" ".join(clean_text(part).split()) for part in parts if part]
    query = "\n".join(line for line in lines if line)
    return query[:QUERY_MAX_CHARS].rstrip()
