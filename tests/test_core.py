import unittest

from mime_header_folding_encoder.core import (
    fold_header,
    fold_subject,
    _encode_word,
    _needs_encoding,
)


class TestFoldHeader(unittest.TestCase):
    def test_short_value_unchanged(self):
        self.assertEqual(fold_header("Subject: hi"), "Subject: hi")

    def test_no_whitespace_overflow_returned_unchanged(self):
        # A single 100-char token with no spaces: we document that we
        # prefer overflow over corrupting the token.
        long_token = "x" * 100
        self.assertEqual(fold_header(long_token), long_token)

    def test_folds_at_space(self):
        # 40 chars + space + 40 chars = 81 total.
        left = "a" * 40
        right = "b" * 40
        result = fold_header(left + " " + right)
        self.assertEqual(result, left + "\r\n " + right)
        for line in result.split("\r\n"):
            self.assertLessEqual(len(line), 78)

    def test_folds_at_tab(self):
        left = "a" * 40
        right = "b" * 40
        result = fold_header(left + "\t" + right)
        self.assertEqual(result, left + "\r\n " + right)

    def test_multiple_folds(self):
        parts = ["w" * 30 for _ in range(4)]
        value = " ".join(parts)  # 30*4 + 3 spaces = 123
        result = fold_header(value)
        lines = result.split("\r\n")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertLessEqual(len(line), 78)
        # Continuation lines start with a single space.
        self.assertTrue(lines[1].startswith(" "))
        # The reconstructed text (spaces restored) equals the input.
        self.assertEqual(result.replace("\r\n ", " "), value)

    def test_leading_whitespace_collapsed(self):
        value = "   hello world " + "x" * 80
        result = fold_header(value)
        # First line must not start with the collapsed leading spaces.
        self.assertTrue(result.startswith("hello"))

    def test_trailing_whitespace_preserved_on_final_line(self):
        value = ("x" * 40) + " " + ("y" * 40) + "   "
        result = fold_header(value)
        self.assertTrue(result.endswith("y" * 40 + "   "))

    def test_custom_max_len(self):
        result = fold_header("aaaa bbbb", max_len=5)
        self.assertEqual(result, "aaaa\r\n bbbb")

    def test_empty_string(self):
        self.assertEqual(fold_header(""), "")

    def test_continuation_uses_crlf_space(self):
        left = "a" * 50
        right = "b" * 50
        result = fold_header(left + " " + right)
        self.assertIn("\r\n ", result)


class TestFoldSubject(unittest.TestCase):
    def test_pure_ascii_delegates_to_fold_header(self):
        self.assertEqual(fold_subject("plain text"), "plain text")

    def test_non_ascii_encoded_as_single_word(self):
        result = fold_subject("caf\u00e9")
        self.assertIn("=?utf-8?B?", result)
        self.assertTrue(result.endswith("?="))
        # There should be exactly one encoded word.
        self.assertEqual(result.count("=?utf-8?B?"), 1)
        self.assertEqual(result.count("?="), 1)

    def test_mixed_ascii_and_non_ascii(self):
        result = fold_subject("Price: \u20ac5 each")
        # ASCII portion preserved verbatim.
        self.assertIn("Price: ", result)
        # Non-ASCII portion becomes an encoded word.
        self.assertIn("=?utf-8?B?", result)
        self.assertIn("?=", result)

    def test_encoded_word_not_split(self):
        # A long encoded word has no internal spaces, so fold_header
        # cannot break it; it must survive intact.
        long_unicode = "\u00e9" * 60
        result = fold_subject(long_unicode)
        self.assertTrue(result.startswith("=?utf-8?B?"))
        self.assertTrue(result.endswith("?="))
        self.assertNotIn("\r\n", result)

    def test_encoded_value_round_trips(self):
        import base64

        original = "S\u00fc\u00dfwaren & \u00dcberflieger"
        folded = fold_subject(original)
        # Extract every encoded word and decode it to verify fidelity.
        import re

        words = re.findall(r"=\?utf-8\?B\?([^?]*)\?=", folded)
        decoded = "".join(base64.b64decode(w).decode("utf-8") for w in words)
        # ASCII fragments are not captured by the regex, so rebuild by
        # replacing each encoded word in the folded string with its
        # decoded form.
        def repl(m):
            return base64.b64decode(m.group(1)).decode("utf-8")

        unfolded = re.sub(r"=\?utf-8\?B\?([^?]*)\?=", repl, folded)
        # Remove fold continuations to compare with the original.
        unfolded = unfolded.replace("\r\n ", "")
        self.assertEqual(unfolded, original)

    def test_long_mixed_value_gets_folded(self):
        ascii_part = "Subject: " + "a" * 30 + " "
        # Keep the non-ASCII run short enough that the encoded word is
        # not longer than a single line, so folding can still occur at
        # the surrounding whitespace.
        unicode_part = "\u20ac" * 5
        ascii_tail = " " + "b" * 30
        value = ascii_part + unicode_part + ascii_tail
        result = fold_subject(value)
        # Must contain at least one fold.
        self.assertIn("\r\n ", result)
        # Every line within the 78-column limit.
        for line in result.split("\r\n"):
            self.assertLessEqual(len(line), 78)


class TestHelpers(unittest.TestCase):
    def test_needs_encoding_ascii(self):
        self.assertFalse(_needs_encoding("plain text!"))

    def test_needs_encoding_unicode(self):
        self.assertTrue(_needs_encoding("caf\u00e9"))

    def test_encode_word_format(self):
        word = _encode_word("hi")
        self.assertEqual(word, "=?utf-8?B?aGk=?=")


if __name__ == "__main__":
    unittest.main()
