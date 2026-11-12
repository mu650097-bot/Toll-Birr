"""Classic Keno: pick 1-10 of 80, the server draws 20 (hypergeometric).

`nominal_table(n)` gives, for n picks, the multiplier for 0..n hits with probability-weighted mean EXACTLY 1.0
(a fair game) and a hard cap (MAX_NOMINAL). The server then applies the disclosed house edge through the same
`_apply_cabinet_house_edge` scale every cabinet game uses (base RTP 1.0 -> scale = 1 - edge), so the player is
shown and paid `effective_table(n, edge)`.
"""
from math import comb

POOL, DRAW, MAX_PICK = 80, 20, 10
MAX_NOMINAL = 1000.0          # "Max payout x1,000" on the design screens
_GAMMA = 0.62                 # payout ~ (1/probability)^gamma: rarer hit counts pay disproportionately more


def pmf(n, h):
    return comb(n, h) * comb(POOL - n, DRAW - h) / comb(POOL, DRAW)


def min_paying_hits(n):
    return 1 if n == 1 else 2 if n <= 4 else 3 if n <= 8 else 4


def nominal_table(n):
    if not isinstance(n, int) or not 1 <= n <= MAX_PICK:
        raise ValueError("bad keno pick count")
    hmin = min_paying_hits(n)
    raw = [((1.0 / pmf(n, h)) ** _GAMMA if h >= hmin else 0.0) for h in range(n + 1)]

    def mean(scale):
        return sum(pmf(n, h) * min(MAX_NOMINAL, scale * raw[h]) for h in range(n + 1))
    lo, hi = 0.0, 1.0
    while mean(hi) < 1.0:            # grow until the capped mean reaches 1
        hi *= 2.0
        if hi > 1e18:
            raise ValueError("keno table cannot reach fair mean under the cap")
    for _ in range(200):             # bisection on the scale
        mid = (lo + hi) / 2.0
        if mean(mid) < 1.0:
            lo = mid
        else:
            hi = mid
    s = (lo + hi) / 2.0
    return [min(MAX_NOMINAL, s * r) for r in raw]


def effective_table(n, edge):
    k = max(0.0, min(1.0, 1.0 - float(edge)))
    return [round(m * k, 4) for m in nominal_table(n)]


def expected_rtp(n, table):
    return sum(pmf(n, h) * table[h] for h in range(n + 1))
