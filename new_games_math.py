"""Pure game math for Roulette, Bingo, Fast Keno (no Flask/DB). Imported by webapp_api and the tests.

Every table below has an EXACT theoretical RTP (computed, not simulated at runtime) so the configured
house edge is applied by the same disclosed scale factor as the other cabinet games."""
import math

# ------------------------------------------------------------------ Roulette (American layout: 0 and 00 => 38 pockets)
# Every bet type has the same RTP: 36/38 = 94.74 percent (house edge 5.26), close to the 5 percent platform default.
ROULETTE_POCKETS = 38                     # 0..36 plus 37 meaning "00"
ROULETTE_RED = frozenset({1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36})
ROULETTE_BETS = ("number","red","black","odd","even","low","high","dozen","column")
ROULETTE_BASE_RTP = 36.0 / 38.0
ROULETTE_DEFAULT_EDGE = 0.0526

def roulette_label(n):
    return "00" if n == 37 else str(n)

def roulette_color(n):
    if n in (0, 37): return "green"
    return "red" if n in ROULETTE_RED else "black"

def roulette_multiplier(spin, bet, value=None):
    """Gross multiplier (stake included) for a single bet; 0 if it loses. Pays 36x / 3x / 2x."""
    if bet == "number": return 36.0 if spin == value else 0.0
    if spin in (0, 37): return 0.0                      # zero pockets lose every outside bet
    if bet == "red": return 2.0 if spin in ROULETTE_RED else 0.0
    if bet == "black": return 2.0 if spin not in ROULETTE_RED else 0.0
    if bet == "odd": return 2.0 if spin % 2 == 1 else 0.0
    if bet == "even": return 2.0 if spin % 2 == 0 else 0.0
    if bet == "low": return 2.0 if 1 <= spin <= 18 else 0.0
    if bet == "high": return 2.0 if 19 <= spin <= 36 else 0.0
    if bet == "dozen": return 3.0 if (spin - 1) // 12 + 1 == value else 0.0
    if bet == "column": return 3.0 if ((spin - 1) % 3) + 1 == value else 0.0
    return 0.0

def roulette_validate(bet, value):
    """Return (bet, value) or raise ValueError."""
    bet = str(bet or "").lower()
    if bet not in ROULETTE_BETS: raise ValueError("bet must be one of: " + ", ".join(ROULETTE_BETS))
    if bet == "number":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 37: raise ValueError("number bet needs value 0-36 (37 means 00)")
        return bet, value
    if bet in ("dozen", "column"):
        if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3): raise ValueError(bet + " bet needs value 1, 2 or 3")
        return bet, value
    if value is not None: raise ValueError(bet + " bet takes no value")
    return bet, None

# ------------------------------------------------------------------ Fast Keno: pick 4 of 40, 10 balls drawn
# NEW: the player picks 1-8 numbers (design: "Pick 1-8 numbers"). Each pick count has its own pay table (hits -> multiplier), built so every
# table returns ~94.8-95.0% (exact value in FASTKENO_RTP_BY_PICKS). Top prizes are capped at 1000x.
FASTKENO_POOL, FASTKENO_DRAW = 40, 10
FASTKENO_PICK_MIN, FASTKENO_PICK_MAX = 1, 8
FASTKENO_PICK = 4   # default/"quick pick" size and the size used by the old fixed game (kept for compatibility)
FASTKENO_PAYTABLES = {
    1: {1: 3.8},
    2: {2: 16.46},
    3: {2: 4.63, 3: 26.07},
    4: {2: 2.21, 3: 8.03, 4: 68.9},
    5: {3: 5.98, 4: 33.07, 5: 413.43},
    6: {3: 3.31, 4: 11.97, 5: 96.46, 6: 1000.0},
    7: {4: 10.24, 5: 48.47, 6: 562.26, 7: 1000.0},
    8: {4: 6.13, 5: 19.04, 6: 159.95, 7: 1000.0, 8: 1000.0},
}
def fastkeno_rtp(picks):
    t = FASTKENO_PAYTABLES[picks]
    return sum(math.comb(picks, h) * math.comb(FASTKENO_POOL - picks, FASTKENO_DRAW - h) / math.comb(FASTKENO_POOL, FASTKENO_DRAW) * m for h, m in t.items())
FASTKENO_RTP_BY_PICKS = {k: fastkeno_rtp(k) for k in FASTKENO_PAYTABLES}
FASTKENO_PAYTABLE = {0: 0.0, **FASTKENO_PAYTABLES[FASTKENO_PICK]}   # compatibility alias (4-pick table)
FASTKENO_BASE_RTP = FASTKENO_RTP_BY_PICKS[FASTKENO_PICK]

# ------------------------------------------------------------------ Bingo: 5x5 card (free centre), 40 of 75 balls drawn, paid by completed lines
# BINGO_LINE_DIST[j] = exact P(exactly j of the 12 lines complete), enumerated over all 2**24 mark patterns
# and weighted by the hypergeometric number of marked cells (75 balls, 24 card numbers, 40 drawn).
BINGO_DRAWS = 40
BINGO_LINE_DIST = [0.5543688944956798, 0.319201667424655, 0.09892178825370519, 0.02237357782079413, 0.0042497373867566085, 0.0007398825668393385, 0.00012147534810462599, 1.9416441563051187e-05, 3.0960111919700206e-06, 3.814973399594416e-07, 8.031522946514559e-08, 0.0, 2.438140894477634e-09]
BINGO_PAYTABLE = {0: 0.0, 1: 0.8, 2: 2.5, 3: 8.5, 4: 30.0, 5: 105.0, 6: 300.0, 7: 1000.0}   # 8+ lines pays 1000x as well
def bingo_multiplier(lines):
    return BINGO_PAYTABLE.get(lines, 1000.0 if lines > 7 else 0.0)
BINGO_BASE_RTP = sum(p * bingo_multiplier(j) for j, p in enumerate(BINGO_LINE_DIST))
BINGO_LINES = ([[r*5+c for c in range(5)] for r in range(5)] + [[r*5+c for r in range(5)] for c in range(5)]
               + [[i*5+i for i in range(5)], [i*5+4-i for i in range(5)]])

def bingo_make_card(rng):
    """Flat list of 25 numbers (row-major); 0 marks the FREE centre. Column c draws from 15c+1..15c+15."""
    cols = [sorted(rng.sample(range(15*c+1, 15*c+16), 5)) for c in range(5)]
    card = [cols[c][r] for r in range(5) for c in range(5)]
    card[12] = 0
    return card

def bingo_score(card, drawn):
    hit = set(drawn); marked = [(n == 0 or n in hit) for n in card]
    done = [i for i, ln in enumerate(BINGO_LINES) if all(marked[k] for k in ln)]
    return len(done), done, marked
