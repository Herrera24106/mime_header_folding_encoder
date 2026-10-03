"""Fold email headers per RFC 5322 line-length limits.

The module provides two functions:
  * ``fold_subject`` - folds a header value that may contain non-ASCII
    text, using RFC 2047 ``=?charset?encoding?text?=`` encoded words
    when necessary.  Non-ASCII substrings are encoded as a single
    contiguous ``=?utf-8?B?...?=`` word so that round-tripping through
    Python's ``email`` package is reliable.
  * ``fold_header`` - folds an already-ASCII header value (or one that
    the caller has already encoded) by inserting CRLF + single-space
    continuations at whitespace boundaries.

Design decisions (stated plainly so behaviour is predictable):
  * Maximum line length is 78 characters, the RFC 5322 SHOULD limit.
  * A line is defined as the bytes up to and excluding a CRLF; the
    CRLF plus the leading space of the next line do not count against
    the 78-column limit on the *current* line.  (RFC 5322 §2.1.1.)
  * Folding only ever occurs at existing ASCII whitespace.  We never
    inject spaces into an encoded word or into the middle of a token
    that had none, because that would change the semantics of the
    header.
  * When folding would be needed but no whitespace is available at
    which to fold, the value is returned unchanged.  Breaking inside a
    token is semantically incorrect for almost every header type, so
    we prefer to exceed the limit than to corrupt the value.  Callers
    who know their header grammar permits mid-token breaks should
    pre-split the value.
"""

from __future__ import annotations

import base64

__all__ = ["fold_header", "fold_subject"]

MAX_LINE_LEN = 78
CRLF = "\r\n"


def _split_words(value: str) -> list[str]:
    """Split *value* into maximal whitespace-delimited tokens.

    Runs of whitespace are preserved as their own list elements so that
    ``fold_header`` can reconstruct the original spacing exactly when no
    fold is needed, and so it can choose a whitespace run as a fold
    point without losing information.
    """
    words: list[str] = []
    buf = ""
    in_ws = False
    for ch in value:
        is_ws = ch in " \t"
        if in_ws and is_ws:
            buf += ch
        elif not in_ws and not is_ws:
            buf += ch
        else:
            if buf:
                words.append(buf)
            buf = ch
            in_ws = is_ws
    if buf:
        words.append(buf)
    return words


def fold_header(value: str, max_len: int = MAX_LINE_LEN) -> str:
    """Fold an ASCII header *value* to fit within *max_len* columns.

    Folding points are chosen only at runs of spaces or tabs already
    present in *value*.  If a single token is longer than *max_len* and
    no whitespace precedes it on the current line, the token overflows
    rather than being split - see the module docstring for the
    rationale.

    Returns the value with ``\r\n "`` continuations inserted.  When no
    folding is required the value is returned unchanged.
    """
    if len(value) <= max_len:
        return value

    tokens = _split_words(value)
    if not tokens:
        return value

    # Confirm there is at least one whitespace token we could fold at;
    # otherwise return unchanged per the documented policy.
    if not any(tok.isspace() for tok in tokens):
        return value

    lines: list[str] = []
    current = ""

    def append_token(tok: str) -> None:
        nonlocal current
        if not current:
            current = tok
            return
        # Adding tok (a non-ws token) to current requires that we also
        # carry forward the whitespace that preceded tok.  But callers
        # of this closure always pass the whitespace run as part of the
        # preceding context, so here tok is a word and current already
        # ends with the connecting whitespace.
        if len(current) + len(tok) <= max_len:
            current += tok
        else:
            lines.append(current)
            current = tok

    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.isspace():
            # Peek at the following word, if any, to decide whether to
            # keep this whitespace on the current line or use it as a
            # fold point.
            next_word = tokens[i + 1] if i + 1 < n else ""
            if next_word == "":
                # Trailing whitespace - keep it where it is.
                if current:
                    current += tok
                # else: leading trailing ws with no word - drop.
                i += 1
                continue
            if not current:
                # Leading whitespace before the first word; collapse.
                i += 1
                continue
            projected = len(current) + len(tok) + len(next_word)
            if projected <= max_len:
                current += tok
                i += 1
                continue
            # This whitespace is our fold point.
            lines.append(current)
            current = ""
            i += 1
            continue
        else:
            append_token(tok)
            i += 1

    if current:
        lines.append(current)

    if len(lines) <= 1:
        return value
    return (CRLF + " ").join(lines)


def _needs_encoding(text: str) -> bool:
    """True if *text* contains characters outside US-ASCII."""
    return any(ord(ch) > 0x7F for ch in text)


def _encode_word(text: str, charset: str = "utf-8") -> str:
    """Encode *text* as a single ``=?charset?B?base64?=`` word.

    Base64 is preferred over quoted-printable here because it is
    shorter for the typical case of multi-byte UTF-8 payloads and
    avoids ambiguity about where the encoded word ends.
    """
    raw = text.encode(charset)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"=?{charset}?B?{b64}?="


def fold_subject(value: str, max_len: int = MAX_LINE_LEN) -> str:
    """Fold a header *value* that may contain non-ASCII text.

    The value is partitioned into runs of ASCII text and runs of
    non-ASCII text.  Each non-ASCII run becomes one RFC 2047 encoded
    word.  ASCII runs are kept verbatim so that header grammar (colons,
    spaces, equals signs) remains visible to parsers that do not decode
    encoded words.

    After encoding, the result is passed through :func:`fold_header` so
    that overly long lines are split at whitespace.  Encoded words are
    atomic from the folder's perspective: they contain no internal
    spaces, so they will either fit on a line or overflow it - they
    will never be broken mid-word.
    """
    if not _needs_encoding(value):
        return fold_header(value, max_len=max_len)

    out = ""
    buf = ""  # accumulates a contiguous non-ASCII run
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ord(ch) > 0x7F:
            buf += ch
        else:
            if buf:
                out += _encode_word(buf)
                buf = ""
            out += ch
        i += 1
    if buf:
        out += _encode_word(buf)

    return fold_header(out, max_len=max_len)
