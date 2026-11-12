"""Chicken Roast (new): 3 reels x 3 rows, 5 fixed paylines (3 rows + 2 diagonals); the total bet is split evenly over the 5 lines.

Each reel stops on a uniform random position of the same 20-symbol strip and shows the symbol above / on / below it.
A line pays when all three of its symbols match. Pays are multiples of the LINE bet (= stake / 5):
egg x4, pepper x15, coin x30, drumstick x120, flame ("full roast") x800 (nominal). Line wins add up.

Nominal base RTP is the exact mean over all 20^3 stops (see base_rtp()). The server scales every payout by
(1 - edge) / BASE_RTP so the RTP is exactly 1 - edge; the player is shown `effective_table(edge)`
(multiples of the TOTAL bet that ONE winning line pays).
"""
from itertools import product

STRIP = list("FPELPELPECPECPECEECE")
N = len(STRIP)
NAMES = {"E": "egg", "P": "pepper", "C": "coin", "L": "leg", "F": "flame"}
PAY = {"E": 4.0, "P": 15.0, "C": 30.0, "L": 120.0, "F": 800.0}
LINES = [(0, 0, 0), (1, 1, 1), (2, 2, 2), (0, 1, 2), (2, 1, 0)]   # row index used on reel 0,1,2
LINE_COUNT = len(LINES)


def cols(pos):
    return [[STRIP[(p - 1) % N], STRIP[p % N], STRIP[(p + 1) % N]] for p in pos]


def grid(pos):
    c = cols(pos)
    return [[c[k][r] for k in range(3)] for r in range(3)]   # rows x reels


def line_wins(pos):
    """[(line_index, symbol_letter, line_pay_multiple)] for every winning line."""
    c = cols(pos); out = []
    for i, L in enumerate(LINES):
        s = [c[k][L[k]] for k in range(3)]
        if s[0] == s[1] == s[2]:
            out.append((i, s[0], PAY[s[0]]))
    return out


def total_multiplier(pos):
    """Nominal payout as a multiple of the TOTAL stake."""
    return sum(w[2] for w in line_wins(pos)) / LINE_COUNT


def base_rtp():
    return sum(total_multiplier(p) for p in product(range(N), repeat=3)) / N ** 3


def hit_frequency():
    return sum(1 for p in product(range(N), repeat=3) if line_wins(p)) / N ** 3


BASE_RTP = base_rtp()


def effective_table(edge):
    s = max(0.0, min(1.0, 1.0 - float(edge))) / BASE_RTP
    return [{"symbol": NAMES[k], "multiplier": round(v / LINE_COUNT * s, 2)} for k, v in PAY.items()]


assert len(STRIP) == 20 and {k: STRIP.count(k) for k in "EPCLF"} == {"E": 8, "P": 5, "C": 4, "L": 2, "F": 1}
