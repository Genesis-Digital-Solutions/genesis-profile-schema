"""A regra do save das regex de códigos de produto (`product_identification.patterns`) vive aqui
desde a v0.1.171 (era do core, `config/profile_pattern_guard.py`, 14 Nov 2026). Testes portados
do core (`tests/test_product_patterns_redos.py`); a execução palavra a palavra continua no core."""
from __future__ import annotations

import pytest

from genesis_profile_schema.pattern_guard import (
    COST_MAX, LIST_REASONS, MAX_CUSTOM_PATTERNS, PATTERN_MAX_CHARS, REASONS, TOTAL_COST_MAX,
    find_unsafe_patterns, pattern_cost, pattern_refusal)

CATASTROPHIC = r"(\d+)+x"          # exponencial: 30 dígitos levavam minutos no `re`


@pytest.mark.parametrize("pattern,reason", [
    (CATASTROPHIC, "nested_quantifier"),
    (r"(?:[A-Z0-9]+){1,4}", "nested_quantifier"),
    (r"(?:\d?\d?){12}!", "nested_quantifier"),
    (r"(?:[0-9]?[0-9]?){12}x", "nested_quantifier"),
    (r"(?:\d?\d?)+!", "nested_quantifier"),
    (r"(?:\d?){128,}!", "nested_quantifier"),
    (r"(?:(?=\d+)a){2,5}", "nested_quantifier"),
    (r"(a|ab)*c", "alternation_in_quantifier"),
    (r"(A)\d{2}\1", "backreference"),
    (r"HIK \d{4}", "whitespace"),
    (r"HIK\s\d{4}", "whitespace"),
    (r"HIK[ -]\d{4}", "whitespace"),
    (r"\d+\d+x", "too_costly"),
    ("A" * (PATTERN_MAX_CHARS + 1), "too_long"),
    ("(", "invalid_regex"),
    ("  ", "empty"),
    (7, "not_a_string"),
    (None, "not_a_string"),
])
def test_unsafe_patterns_are_refused(pattern, reason):
    assert reason in REASONS
    assert pattern_refusal(pattern) == reason
    assert pattern_cost(pattern) is None


@pytest.mark.parametrize("pattern", [
    r"[A-Z]{3}\d{4,}", r"(HIK|DS)-\d{4,8}", r"[A-Z]{2,5}[-_]?\d{3,12}[A-Z0-9]{0,6}", r"\bSKU\d{5}\b",
    r"(?:[A-Z]{2}-){3}\d{4}",            # repetição exata dentro de repetição: sem escolha, aceite
    r"[^\s]{2}\d{3}",                    # classe negada com \s: não casa espaço
])
def test_reasonable_patterns_pass(pattern):
    assert pattern_refusal(pattern) is None
    assert 1 <= pattern_cost(pattern) <= COST_MAX


def test_find_unsafe_patterns_gives_path_and_reason_never_the_value():
    doc = {"product_identification": {"enabled": True, "patterns": [r"[A-Z]{3}\d{4,}", CATASTROPHIC]}}
    assert find_unsafe_patterns(doc) == ["product_identification.patterns.1: nested_quantifier"]
    too_many = {"product_identification": {"patterns": [r"SKU\d{5}"] * (MAX_CUSTOM_PATTERNS + 1)}}
    assert find_unsafe_patterns(too_many)[0].startswith("product_identification.patterns: too_many")
    assert find_unsafe_patterns({"product_identification": {"patterns": []}}) == []
    assert find_unsafe_patterns({"product_identification": {"patterns": "x+"}}) == [
        "product_identification.patterns: not_a_list"]
    # orçamento somado: dois padrões aceites um a um, caros demais juntos
    pricey = r"[A-Z]{1,8}\d{1,8}[A-Z0-9]{0,47}"            # 8 × 8 × 48 = 3072
    assert pattern_refusal(pricey) is None and pattern_cost(pricey) == 3072
    total = find_unsafe_patterns({"product_identification": {"patterns": [pricey] * 2}})
    assert total == [f"product_identification.patterns: too_costly_total (6144 > {TOTAL_COST_MAX})"]
    for doc in ({}, None, [], {"product_identification": None}, {"product_identification": {}}):
        assert find_unsafe_patterns(doc) == []
    every = {line.split(": ", 1)[1].split(" ", 1)[0]
             for line in find_unsafe_patterns(too_many) + total}
    assert every <= set(LIST_REASONS)


def test_a_huge_list_is_capped_and_the_value_never_enters_the_cache():
    from genesis_profile_schema import pattern_guard
    huge = {"product_identification": {"patterns": ["x" * 10_000] * 1_000}}
    before = pattern_guard._analyse.cache_info().currsize
    out = find_unsafe_patterns(huge)
    assert pattern_guard._analyse.cache_info().currsize == before
    assert out[0].startswith("product_identification.patterns: too_many")
    assert len(out) == 1 + MAX_CUSTOM_PATTERNS * 5
    assert all("xxxx" not in line for line in out)


def test_package_exports_the_guard():
    import genesis_profile_schema as g
    assert g.pattern_refusal is pattern_refusal and g.find_unsafe_patterns is find_unsafe_patterns
