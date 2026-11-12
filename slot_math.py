"""Slots (new): 5 reels x 3 rows, 10 fixed paylines, Wild, Scatter + Free Spins.  ONE engine ("slot") behind all 36 themed slot games;
a theme only changes the pictures, never the maths.

Each reel stops on a uniform random position of its own 24-symbol strip and shows the symbol above / on / below it (cyclic).
Lines pay left to right from reel 1: 3 / 4 / 5 of a kind. Wild (reels 2-4 only) substitutes for every symbol except Scatter.
Pays are multiples of the LINE bet (= stake / 10); line wins add up. Scatter (any position) pays a multiple of the TOTAL bet for 3/4/5
and 3 or more scatters award FREE_SPINS free spins: same strips, every line win doubled, no scatter pay and no re-trigger inside the bonus.

BASE_RTP is exact (computed below by enumeration, no simulation). The server scales every payout by (1 - edge) / BASE_RTP so the
RTP equals 1 - edge; the player is shown effective_table(edge).
"""
from itertools import product
from fractions import Fraction

REELS, ROWS, N = 5, 3, 24
SYMS = ["a", "b", "c", "d", "e", "W", "S"]            # a = lowest ... e = top symbol, W = wild, S = scatter
COUNTS = [   # symbols per reel strip (each row sums to 24)
    {"a": 8, "b": 6, "c": 4, "d": 3, "e": 2, "W": 0, "S": 1},   # reel 1
    {"a": 6, "b": 6, "c": 4, "d": 3, "e": 2, "W": 2, "S": 1},   # reel 2
    {"a": 6, "b": 6, "c": 4, "d": 3, "e": 2, "W": 2, "S": 1},   # reel 3
    {"a": 6, "b": 6, "c": 4, "d": 3, "e": 2, "W": 2, "S": 1},   # reel 4
    {"a": 8, "b": 6, "c": 4, "d": 3, "e": 2, "W": 0, "S": 1},   # reel 5
]
PAY = {"a": {3: 2.0, 4: 6.0, 5: 16.0}, "b": {3: 4.0, 4: 10.0, 5: 30.0}, "c": {3: 6.0, 4: 20.0, 5: 60.0},
       "d": {3: 10.0, 4: 40.0, 5: 120.0}, "e": {3: 20.0, 4: 100.0, 5: 400.0}}
SCATTER_PAY = {3: 4.0, 4: 20.0, 5: 100.0}              # x TOTAL bet
FREE_SPINS, FS_MULT = 8, 2.0
LINES = [(1,1,1,1,1), (0,0,0,0,0), (2,2,2,2,2), (0,1,2,1,0), (2,1,0,1,2), (0,0,1,2,2), (2,2,1,0,0), (1,0,0,0,1), (1,2,2,2,1), (0,1,1,1,0)]
LINE_COUNT = len(LINES)

def strip(k):
    """Deterministic strip for reel k: symbols spread out (round-robin by count) so equal symbols are rarely adjacent."""
    left = dict(COUNTS[k]); out = []; order = ["a", "b", "c", "a", "d", "b", "a", "e", "c", "W", "S", "b"]
    while len(out) < N:
        for s in order:
            if left.get(s, 0) > 0 and len(out) < N:
                out.append(s); left[s] -= 1
    assert len(out) == N and sorted(out) == sorted(sum(([s] * c for s, c in COUNTS[k].items()), [])), "strip counts"
    return out
STRIPS = [strip(k) for k in range(REELS)]

def window(pos, k):
    st = STRIPS[k]; return [st[(pos - 1) % N], st[pos % N], st[(pos + 1) % N]]   # top, middle, bottom
def grid(positions):
    cols = [window(p, k) for k, p in enumerate(positions)]
    return [[cols[k][r] for k in range(REELS)] for r in range(ROWS)]                # rows x reels

def line_pay(symbols):
    """(multiple of line bet, paying symbol, count) for one 5-symbol line; Wild substitutes, Scatter breaks a run."""
    first = next((s for s in symbols if s != "W"), "W")
    if first == "S": return 0.0, None, 0
    if first == "W": first = "e"                      # five wilds = top symbol pay
    n = 0
    for s in symbols:
        if s == first or s == "W": n += 1
        else: break
    p = PAY[first].get(n, 0.0) if n >= 3 else 0.0
    return p, first, n

def evaluate(g):
    """Every winning line of a grid -> (list of wins, line_total_in_LINE_bets)."""
    wins = []; tot = 0.0
    for i, L in enumerate(LINES):
        syms = [g[L[k]][k] for k in range(REELS)]
        p, s, n = line_pay(syms)
        if p > 0: wins.append({"line": i, "symbol": s, "count": n, "pay": p}); tot += p
    return wins, tot
def scatter_count(g): return sum(row.count("S") for row in g)

def multiplier_of_spin(g, bonus=False):
    """Total-bet multiple of ONE spin (before the house-edge scale)."""
    wins, tot = evaluate(g); m = tot / LINE_COUNT
    if bonus: return m * FS_MULT
    return m

# ------------------------------------------------------------ exact RTP (enumeration over symbol combinations on ONE line, then x LINE_COUNT / LINE_COUNT)
def _reel_prob(k): return {s: Fraction(c, N) for s, c in COUNTS[k].items() if c}
def _line_expectation():
    probs = [_reel_prob(k) for k in range(REELS)]; tot = Fraction(0)
    for combo in product(*[list(p.items()) for p in probs]):
        pr = Fraction(1); syms = []
        for s, q in combo: pr *= q; syms.append(s)
        p, _, _ = line_pay(syms)
        if p: tot += pr * Fraction(p).limit_denominator(1000)
    return tot                                         # E[pay of one line] in line-bet units == RTP share in TOTAL-bet units
def _scatter_dist():
    dist = [Fraction(1)]
    for k in range(REELS):
        per = [0] * 4
        for pos in range(N): per[window(pos, k).count("S")] += 1
        per = [Fraction(x, N) for x in per]; nd = [Fraction(0)] * (len(dist) + 3)
        for i, a in enumerate(dist):
            for j, b in enumerate(per): nd[i + j] += a * b
        dist = nd
    return dist
LINE_RTP = _line_expectation()
SCATTER_DIST = _scatter_dist()
P_TRIGGER = sum(SCATTER_DIST[3:])
SCATTER_RTP = sum(SCATTER_DIST[k] * Fraction(SCATTER_PAY[min(k, 5)]).limit_denominator(1000) for k in range(3, min(6, len(SCATTER_DIST))))
BONUS_VALUE = FREE_SPINS * Fraction(FS_MULT).limit_denominator(1000) * LINE_RTP     # expected total-bet multiple of one whole free-spin round
BASE_RTP = float(LINE_RTP + SCATTER_RTP + P_TRIGGER * BONUS_VALUE)
HIT_FREQ_NOTE = None

def effective_table(edge):
    s = (1.0 - edge) / BASE_RTP
    return {"pay": {sym: {str(n): round(v * s, 4) for n, v in t.items()} for sym, t in PAY.items()},   # multiples of the LINE bet
            "scatter": {str(n): round(v * s, 4) for n, v in SCATTER_PAY.items()}, "free_spins": FREE_SPINS, "fs_mult": FS_MULT, "scale": s}

def spin_round(rng):
    """One paid round: base spin (+ free spins when 3+ scatters). Returns (outcome dict, nominal total-bet multiple)."""
    pos = [rng.randrange(N) for _ in range(REELS)]; g = grid(pos); wins, tot = evaluate(g)
    sc = scatter_count(g); base_m = tot / LINE_COUNT; scat_m = SCATTER_PAY.get(min(sc, 5), 0.0) if sc >= 3 else 0.0
    spins = []; fs_m = 0.0
    if sc >= 3:
        for _ in range(FREE_SPINS):
            p2 = [rng.randrange(N) for _ in range(REELS)]; g2 = grid(p2); w2, t2 = evaluate(g2); m2 = t2 / LINE_COUNT * FS_MULT
            spins.append({"grid": g2, "wins": w2, "mult": m2}); fs_m += m2
    total = base_m + scat_m + fs_m
    return {"grid": g, "wins": wins, "scatters": sc, "scatter_mult": scat_m, "base_mult": base_m, "free_spins": spins, "fs_mult_total": fs_m}, total

if __name__ == "__main__":
    print("line RTP %.4f  scatter RTP %.4f  P(trigger) %.5f  bonus value %.2fx  BASE_RTP %.4f" % (float(LINE_RTP), float(SCATTER_RTP), float(P_TRIGGER), float(BONUS_VALUE), BASE_RTP))
    import random; r = random.Random(1); n = 200000; tot = 0; hits = 0; mx = 0
    for _ in range(n):
        o, m = spin_round(r); tot += m; hits += m > 0; mx = max(mx, m)
    print("sim RTP %.4f hit %.3f max %.1fx" % (tot / n, hits / n, mx))
