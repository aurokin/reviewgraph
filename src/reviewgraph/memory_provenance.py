from __future__ import annotations

import re


def memory_body_overlaps_text(memory_body: str | None, text: str) -> bool:
    if not memory_body:
        return False
    normalized_memory = _normalize_memory_text(memory_body)
    normalized_text = _normalize_memory_text(text)
    if _exact_memory_body_is_meaningful(normalized_memory) and _normalized_phrase_in_text(
        normalized_memory,
        normalized_text,
    ):
        return True
    text_words = set(normalized_text.split())
    meaningful_fragments = _meaningful_memory_fragments(memory_body)
    for raw_token in (token for token in re.split(r"\s+", memory_body.strip()) if token):
        compact_token = _compact_raw_token(raw_token)
        if (
            compact_token
            and _raw_token_has_delimiter_signal(raw_token)
            and _has_meaningful_delimited_alpha_token_signal(compact_token)
            and _compact_fragment_in_text(compact_token, normalized_text)
        ):
            return True
    for fragment in meaningful_fragments:
        if (
            " " in fragment
            and (_has_enough_fragment_signal(fragment) or fragment == normalized_memory)
            and _normalized_phrase_in_text(fragment, normalized_text)
        ):
            return True
        if " " not in fragment and fragment in text_words:
            return True
        compact_fragment = fragment.replace(" ", "")
        if " " not in fragment and _looks_mixed_identifier_like(fragment) and _compact_fragment_in_text(
            compact_fragment,
            normalized_text,
        ):
            return True
        if (
            " " in fragment
            and (
                _has_enough_compact_fragment_signal(compact_fragment)
                or (
                    _has_enough_fragment_signal(fragment)
                    and _has_meaningful_compact_raw_token_signal(compact_fragment, fragment.split(), 0)
                )
            )
            and _compact_fragment_in_text(compact_fragment, normalized_text)
        ):
            return True
    return False


def _meaningful_memory_fragments(memory_body: str) -> tuple[str, ...]:
    normalized = _normalize_memory_text(memory_body)
    raw_tokens = [token for token in re.split(r"\s+", memory_body.strip()) if token]
    fragments = {normalized} if _full_memory_fragment_is_meaningful(normalized) else set()
    for sentence in normalized.replace("!", ".").replace("?", ".").split("."):
        sentence = sentence.strip()
        if len(sentence) >= 16:
            fragments.add(sentence)
    words = normalized.split()
    for index, word in enumerate(words):
        if _has_enough_word_signal(word, words, index):
            fragments.add(word)
    for index, raw_token in enumerate(raw_tokens):
        compact_token = _compact_raw_token(raw_token)
        if compact_token and (
            _raw_token_has_high_signal_context(raw_tokens, index)
            or _raw_token_has_delimiter_digit_signal(raw_token)
            or _raw_token_has_delimiter_signal(raw_token)
        ) and _has_meaningful_compact_raw_token_signal(compact_token, words, index):
            fragments.add(compact_token)
    for size in range(2, min(5, len(words)) + 1):
        for index in range(0, len(words) - size + 1):
            fragment = " ".join(words[index : index + size])
            raw_fragment = " ".join(raw_tokens[index : index + size])
            if _has_enough_fragment_signal(fragment) or _has_enough_compact_fragment_signal(
                fragment,
                raw_fragment,
            ):
                fragments.add(fragment)
    for index in range(0, max(len(words) - 5, 0)):
        fragment = " ".join(words[index : index + 6])
        if len(fragment) >= 24:
            fragments.add(fragment)
    return tuple(sorted(fragments))


def _has_enough_fragment_signal(fragment: str) -> bool:
    if _is_common_numeric_memory_fragment(fragment):
        return False
    words = fragment.split()
    if len(words) >= 3:
        return len(fragment) >= 10 and len(set(fragment.replace(" ", ""))) >= 5
    if len(words) == 2:
        sensitive_words = {"account", "codename", "identifier", "key", "password", "secret", "ticket", "token"}
        return (
            len(fragment) >= 10
            and len(set(fragment.replace(" ", ""))) >= 5
            and (any(word in sensitive_words for word in words) or not all(word in _COMMON_MEMORY_WORDS for word in words))
        )
    compact = fragment.replace(" ", "")
    return len(fragment) >= 7 and len(set(compact)) >= 5


def _is_common_numeric_memory_fragment(normalized: str) -> bool:
    words = normalized.split()
    if len(words) != 2:
        return False
    first, second = words
    return (first in _COMMON_MEMORY_WORDS and second.isdigit()) or (first.isdigit() and second in _COMMON_MEMORY_WORDS)


def _exact_memory_body_is_meaningful(normalized: str) -> bool:
    words = normalized.split()
    if not words:
        return False
    if all(word in _COMMON_MEMORY_WORDS for word in words):
        return False
    compact = normalized.replace(" ", "")
    if compact in _COMMON_TECH_TOKENS:
        return False
    if _is_common_numeric_memory_fragment(normalized):
        return False
    if len(words) == 1:
        word = words[0]
        if word in _COMMON_TECH_TOKENS:
            return False
        return word not in _COMMON_MEMORY_WORDS and len(word) >= 4 and len(set(word)) >= 4
    return len(normalized) >= 4 and len(set(normalized.replace(" ", ""))) >= 4


def _normalized_phrase_in_text(phrase: str, text: str) -> bool:
    words = phrase.split()
    if len(words) == 1:
        return words[0] in set(text.split())
    return f" {phrase} " in f" {text} "


def _compact_fragment_in_text(compact_fragment: str, normalized_text: str) -> bool:
    words = normalized_text.split()
    for size in range(1, min(4, len(words)) + 1):
        for index in range(0, len(words) - size + 1):
            if "".join(words[index : index + size]) == compact_fragment:
                return True
    if _high_signal_compact_fragment(compact_fragment) and compact_fragment in normalized_text.replace(" ", ""):
        return True
    return False


def _high_signal_compact_fragment(compact_fragment: str) -> bool:
    if compact_fragment in _COMMON_TECH_TOKENS or _common_word_numeric_prefix(compact_fragment) is not None:
        return False
    return len(compact_fragment) >= 5 and (
        _looks_mixed_identifier_like(compact_fragment)
        or any(token in compact_fragment for token in ("secret", "codename"))
    )


def _full_memory_fragment_is_meaningful(normalized: str) -> bool:
    return " " in normalized and _exact_memory_body_is_meaningful(normalized)


def _has_enough_word_signal(word: str, words: list[str], index: int) -> bool:
    if word in _COMMON_MEMORY_WORDS or word in _COMMON_TECH_TOKENS:
        return False
    if len(words) == 1:
        return len(word) >= 5 and len(set(word)) >= 4
    context_window = words[max(0, index - 2) : index] + words[index + 1 : index + 3]
    if _looks_identifier_like(word):
        if _looks_mixed_identifier_like(word):
            return True
        return any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)
    if len(word) >= 10 and len(set(word)) >= 6:
        return True
    return len(word) >= 5 and len(set(word)) >= 4 and any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)


def _looks_identifier_like(word: str) -> bool:
    return any(char.isdigit() for char in word) and len(word) >= 6 and len(set(word)) >= 4


def _looks_mixed_identifier_like(word: str) -> bool:
    if word in _COMMON_TECH_TOKENS:
        return False
    return (
        any(char.isalpha() for char in word)
        and any(char.isdigit() for char in word)
        and len(word) >= 6
        and len(set(word)) >= 4
    )


def _has_enough_compact_fragment_signal(fragment: str, raw_fragment: str = "") -> bool:
    compact = fragment.replace(" ", "")
    words = fragment.split()
    return _has_meaningful_compact_raw_token_signal(compact, words, 0) and (
        _looks_identifier_like(compact) or _has_high_signal_context(words, raw_fragment)
    )


def _has_high_signal_context(words: list[str], raw_fragment: str) -> bool:
    return any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in words) or bool(
        re.search(
            r"[A-Za-z]+(?:[^\w\s]|_)[A-Za-z0-9]*\d|\d(?:[^\w\s]|_)[A-Za-z0-9]+|[A-Za-z]+(?:[^\w\s]|_)[A-Za-z]+",
            raw_fragment,
        )
    )


def _compact_raw_token(raw_token: str) -> str | None:
    if not re.search(r"(?:[^\w\s]|_)", raw_token):
        return None
    compact = _normalize_memory_text(raw_token).replace(" ", "")
    if len(compact) < 5 or len(set(compact)) < 4:
        return None
    return compact


def _raw_token_has_high_signal_context(raw_tokens: list[str], index: int) -> bool:
    token = _normalize_memory_text(raw_tokens[index])
    if any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in token.split()):
        return True
    context_tokens = raw_tokens[max(0, index - 2) : index] + raw_tokens[index + 1 : index + 3]
    context = _normalize_memory_text(" ".join(context_tokens)).split()
    return any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in context)


def _raw_token_has_delimiter_signal(raw_token: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]+(?:[^\w\s]|_)[A-Za-z0-9]+", raw_token))


def _raw_token_has_delimiter_digit_signal(raw_token: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]+(?:[^\w\s]|_)[A-Za-z0-9]*\d|\d(?:[^\w\s]|_)[A-Za-z0-9]+", raw_token))


def _has_meaningful_compact_raw_token_signal(compact_token: str, words: list[str], index: int) -> bool:
    if compact_token in _COMMON_TECH_TOKENS:
        return False
    context_window = words[max(0, index - 2) : index] + words[index + 1 : index + 3]
    prefix = _common_word_numeric_prefix(compact_token)
    if prefix is not None:
        return prefix in _IDENTIFIER_NUMERIC_PREFIX_WORDS or any(
            token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window
        )
    if compact_token.isdigit():
        return any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)
    return _looks_mixed_identifier_like(compact_token) or len(compact_token) >= 5


def _has_meaningful_delimited_alpha_token_signal(compact_token: str) -> bool:
    return (
        compact_token.isalpha()
        and compact_token not in _COMMON_MEMORY_WORDS
        and compact_token not in _COMMON_TECH_TOKENS
        and len(compact_token) >= 5
        and len(set(compact_token)) >= 4
    )


def _common_word_numeric_prefix(compact_token: str) -> str | None:
    return next(
        (
            word
            for word in _COMMON_MEMORY_WORDS
            if compact_token.startswith(word) and compact_token[len(word) :].isdigit()
        ),
        None,
    )


def _normalize_memory_text(value: str) -> str:
    return " ".join(re.sub(r"[_\W]+", " ", value.casefold()).split())


_IDENTIFIER_NUMERIC_PREFIX_WORDS = {
    "customer",
    "user",
}


_COMMON_MEMORY_WORDS = {
    "authentication",
    "authorization",
    "become",
    "branch",
    "cache",
    "candidate",
    "change",
    "comment",
    "commenter",
    "customer",
    "during",
    "evidence",
    "here",
    "if",
    "issue",
    "line",
    "mentioned",
    "never",
    "patch",
    "payload",
    "please",
    "public",
    "referenced",
    "review",
    "reviewer",
    "should",
    "target",
    "the",
    "thread",
    "untrusted",
    "version",
}

_HIGH_SIGNAL_CONTEXT_WORDS = {
    "account",
    "codename",
    "identifier",
    "key",
    "secret",
    "ticket",
    "token",
}

_COMMON_TECH_TOKENS = {
    "go122",
    "grpc",
    "http2",
    "json",
    "node18",
    "oauth",
    "python3",
    "react19",
    "sha256",
    "yaml",
}
