def normalize_markdown(text: str) -> str:
    """Strip a leading BOM and convert CRLF and lone CR line endings to LF."""
    return text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")
