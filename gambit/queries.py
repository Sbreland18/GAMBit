"""Google Admin search queries built from names GAMbit doesn't control."""

from __future__ import annotations


def quote(value: str) -> str:
    """A value for a Directory API query: inside single quotes, with \\ and ' escaped –
    an org unit like “/O'Brien Elementary” would otherwise end the quotes early."""
    v = str(value or "").replace("\\", "\\\\").replace("'", "\\'")
    return f"'{v}'"


def ou(path: str) -> str:
    return f"orgUnitPath={quote(path)}"
