"""Two-dice Under / Exact / Over math (pure, no Flask / DB). The sum of two fair dice is 2..12;
P(sum = k) = (6 - |k - 7|) / 36. Payout = (1 - edge) / P, so every valid bet has the same RTP."""
DICE2_MAX_CHANCE = 0.90      # a bet that wins more often than this would pay <= ~1.05x: not offered

def _cnt(k): return 6 - abs(k - 7) if 2 <= k <= 12 else 0

def dice2_chance(mode, target):
    """Exact win probability, or 0.0 when the bet is impossible."""
    try: t = int(target)
    except (TypeError, ValueError): return 0.0
    if mode == "under": n = sum(_cnt(k) for k in range(2, t))
    elif mode == "over": n = sum(_cnt(k) for k in range(t + 1, 13))
    elif mode == "exact": n = _cnt(t)
    else: return 0.0
    return n / 36.0

def dice2_valid(mode, target):
    """(ok, error). A bet is valid when it can win and does not win more than 90% of the time."""
    if mode not in ("under", "exact", "over"): return False, "mode must be under, exact or over"
    try: t = int(target)
    except (TypeError, ValueError): return False, "target must be 2-12"
    if not 2 <= t <= 12: return False, "target must be 2-12"
    p = dice2_chance(mode, t)
    if p <= 0: return False, "this bet can never win"
    if p > DICE2_MAX_CHANCE: return False, "this bet wins too often (max win chance 90%)"
    return True, ""

def dice2_won(mode, target, total):
    t = int(target)
    return total < t if mode == "under" else total > t if mode == "over" else total == t
