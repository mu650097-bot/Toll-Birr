"""Plinko with Risk (low/med/high) and Rows (8/12/16).

Fair binomial ball: every peg is an independent 50/50, so bucket k of `rows` has probability C(rows,k)/2^rows.
`nominal_table` returns multipliers whose probability-weighted mean is EXACTLY 1.0 (a fair game); the server
then applies the disclosed house edge through the same `_apply_cabinet_house_edge` scale every cabinet game
uses (base RTP 1.0 -> scale = 1 - edge). `effective_table(edge)` is what the player is shown and paid.
The legacy 8-row / 9-bucket Plinko is untouched and is still used when no risk/rows are sent.
"""
from math import comb

RISKS = ("low", "med", "high")
ROWS = (8, 12, 16)

# raw shape = floor + span * x**power, x = distance from the centre bucket (0 centre .. 1 edge).
# A larger power / span concentrates the payout in rare edge buckets (higher variance).
_SHAPE = {"low": (0.55, 6.0, 3.0), "med": (0.25, 24.0, 4.0), "high": (0.10, 160.0, 6.0)}


def probs(rows):
    n = 2 ** rows
    return [comb(rows, k) / n for k in range(rows + 1)]


def nominal_table(risk, rows):
    if risk not in _SHAPE or rows not in ROWS:
        raise ValueError("bad plinko risk/rows")
    floor, span, power = _SHAPE[risk]
    p = probs(rows)
    raw = []
    for k in range(rows + 1):
        x = abs(k - rows / 2) / (rows / 2)
        raw.append(floor + span * x ** power)
    mean = sum(pi * ri for pi, ri in zip(p, raw))
    return [ri / mean for ri in raw]          # sum(p*m) == 1.0


def effective_table(risk, rows, edge):
    s = max(0.0, min(1.0, 1.0 - float(edge)))
    return [round(m * s, 4) for m in nominal_table(risk, rows)]


def expected_rtp(table, rows):
    return sum(pi * mi for pi, mi in zip(probs(rows), table))
