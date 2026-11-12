"""Buffalo Plains: 5 reels x 3 rows, 243 WAYS (left to right, adjacent reels), scatter-triggered free spins.

Every reel stops on a uniform random position of the same 30-symbol strip and shows the symbol above / on / below it.
A symbol pays for 3, 4 or 5 adjacent reels counted from the LEFT; the number of ways is the product of how many of that
symbol are visible on each of those reels. Pays are multiples of the TOTAL stake per way. Ways add up.
Three or more COIN scatters anywhere start the Stampede Bonus: 8 / 12 / 20 free spins (3 / 4 / 5 coins) at the same
stake, every free-spin win paid x2; coins inside free spins do not retrigger.

The exact RTP is computed analytically (reels are independent): see base_rtp(). The server scales every payout by
(1 - edge) / BASE_RTP, so the RTP is exactly 1 - edge. The player is shown `effective_table(edge)`.
"""
from itertools import product

STRIP = ["J", "Q", "K", "J", "A", "Q", "C", "J", "K", "W", "Q", "J", "E", "K", "A", "J", "Q", "B", "J", "K",
         "Q", "C", "J", "A", "K", "Q", "W", "J", "E", "$"]
N = len(STRIP)
NAMES = {"J": "J", "Q": "Q", "K": "K", "A": "A", "C": "cactus", "W": "wolf", "E": "eagle", "B": "buffalo", "$": "coin"}
PAY = {  # multiples of the total stake PER WAY for 3 / 4 / 5 reels
    "J": (0.16, 0.48, 1.60), "Q": (0.20, 0.60, 2.00), "K": (0.24, 0.80, 2.40), "A": (0.32, 1.00, 3.20),
    "C": (0.40, 1.60, 4.80), "W": (0.60, 2.40, 8.00), "E": (1.00, 4.00, 16.00), "B": (2.00, 10.00, 40.00),
}
SCATTER = "$"
FREE_SPINS = {3: 8, 4: 12, 5: 20}
FS_MULT = 2.0


def window(p):
    return [STRIP[(p - 1) % N], STRIP[p % N], STRIP[(p + 1) % N]]


def grid(pos):
    """3 rows x 5 reels."""
    cols = [window(p) for p in pos]
    return [[cols[c][r] for c in range(5)] for r in range(3)]


def ways_wins(pos):
    """[(symbol_letter, reels_matched, ways, multiple_of_stake)] for the 243-ways evaluation of one spin."""
    cols = [window(p) for p in pos]; out = []
    for s in PAY:
        counts = [c.count(s) for c in cols]
        k = 0
        while k < 5 and counts[k] > 0:
            k += 1
        if k >= 3:
            ways = 1
            for i in range(k):
                ways *= counts[i]
            out.append((s, k, ways, ways * PAY[s][k - 3]))
    return out


def scatter_count(pos):
    return sum(c.count(SCATTER) for c in (window(p) for p in pos))


def spin_multiple(pos):
    return sum(w[3] for w in ways_wins(pos))


def _dist(sym):
    """Per-reel distribution of how many `sym` are visible: {count: probability}."""
    d = {}
    for p in range(N):
        c = window(p).count(sym); d[c] = d.get(c, 0) + 1.0 / N
    return d


def ways_rtp():
    """Exact expected ways multiple of ONE spin (reels independent): sum_k pay * prod_{i<k} E[c] * P(c_k == 0)."""
    total = 0.0
    for s, pays in PAY.items():
        d = _dist(s); e = sum(c * p for c, p in d.items()); p0 = d.get(0, 0.0)
        for k in (3, 4, 5):
            total += pays[k - 3] * e ** k * (p0 if k < 5 else 1.0)
    return total


def scatter_probs():
    """P(total coins == n) over 5 reels."""
    d = _dist(SCATTER); dist = {0: 1.0}
    for _ in range(5):
        nd = {}
        for a, pa in dist.items():
            for c, pc in d.items():
                nd[a + c] = nd.get(a + c, 0.0) + pa * pc
        dist = nd
    return dist


def feature_rtp():
    pr = scatter_probs(); R = ways_rtp()
    return sum(pr.get(n, 0.0) * FREE_SPINS[n] * FS_MULT * R for n in FREE_SPINS)


def trigger_probability():
    pr = scatter_probs(); return sum(pr.get(n, 0.0) for n in FREE_SPINS)


def base_rtp():
    return ways_rtp() + feature_rtp()


BASE_RTP = base_rtp()


def hit_frequency():
    """Exact P(a base spin has at least one ways win) by enumeration over per-reel windows (30^5 = 24M too big):
    estimated analytically via the complement over symbols is not independent, so use a fixed-seed Monte Carlo."""
    import random
    rng = random.Random(12345); n = 200000; h = 0
    for _ in range(n):
        if ways_wins([rng.randrange(N) for _ in range(5)]):
            h += 1
    return h / n


def effective_table(edge):
    s = max(0.0, min(1.0, 1.0 - float(edge))) / BASE_RTP
    return [{"symbol": NAMES[k], "x3": round(v[0] * s, 2), "x4": round(v[1] * s, 2), "x5": round(v[2] * s, 2)} for k, v in PAY.items()]


assert len(STRIP) == 30 and all(STRIP.count(k) > 0 for k in NAMES)
