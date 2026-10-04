# MIME Header Folding Encoder

Folds long email header lines to fit the RFC 5322 78-column limit, with RFC 2047 encoded-word support for non-ASCII text.

## Usage

```python
from mime_header_folding_encoder import fold_header, fold_subject

# ASCII value: folds at existing whitespace.
folded = fold_header("Subject: " + "word " * 20)

# Non-ASCII value: encodes runs of non-ASCII as =?utf-8?B?...?= words,
# then folds the result.
folded = fold_subject("Subject: Café menus for €5 — see attached")
```

## Why this exists

Email headers are limited to 78 columns per line (RFC 5322 §2.1.1). Values longer than that must be *folded* by inserting `CRLF` followed by linear whitespace. Non-ASCII header content additionally requires RFC 2047 encoded words, because raw UTF-8 bytes are not legal in a header.

This library handles both concerns in one call. The trade-off: folding only happens at whitespace that already exists in the value. If a single token (or encoded word) is longer than 78 characters and sits at the start of a line, it overflows rather than being split mid-token. Splitting a token would change the meaning of the header for most grammars, so overflow is the safer failure mode.

## Edge cases you will hit

- A header value with no whitespace at all (e.g. a long base64 blob) cannot be folded and is returned unchanged.
- A single encoded word representing many non-ASCII characters has no internal whitespace, so it too is atomic and may overflow. If you need shorter encoded words, pre-split your non-ASCII text before calling `fold_subject`.
- The library targets the 78-column SHOULD limit, not the 998-column MUST limit. If you need 998, pass `max_len=998`.

## Exported names

- `fold_header(value: str, max_len: int = 78) -> str` — folds an ASCII header value.
- `fold_subject(value: str, max_len: int = 78) -> str` — encodes non-ASCII runs as RFC 2047 words, then folds.
