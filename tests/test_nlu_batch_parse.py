"""NLU parse: batch lines + max_tokens."""
from __future__ import annotations

import logging
from typing import Any

from bot.services.nlu_parser import TransactionNLUParser, _split_transaction_batches

log = logging.getLogger("finance.nlu.batch")


def test_split_transaction_batches_multiline():
    text = "a\n\nb\nc\n"
    batches = _split_transaction_batches(text, chunk_lines=10)
    assert batches == ["a", "b", "c"]


def test_split_single_block():
    assert _split_transaction_batches("one line only", chunk_lines=10) == ["one line only"]


def test_merge_parse_results():
    parser = TransactionNLUParser()
    a = {"transactions": [{"type": "expense", "amount": 1}]}
    b = {"type": "transfer", "amount": 2}
    c = {"transactions": [{"type": "income", "amount": 3}]}
    merged = parser._merge_parse_responses([a, b, c])
    assert len(merged) == 3
    assert merged[0]["amount"] == 1
    assert merged[1]["amount"] == 2
    assert merged[2]["amount"] == 3
