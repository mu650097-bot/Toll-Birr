"""Pure card-game logic for Baccarat and Blackjack (no Flask / DB). Cards are ints 0..51: rank=(c%13)+1 (1=A..13=K), suit=c//13."""
import hashlib, random

# ---------------------------------------------------------------- Baccarat (punto banco, 8 decks)
# Exact probabilities by enumeration of an 8-deck shoe without replacement (see tests/bacc_exact check in
# baccarat_regression_test.py, which re-derives them). Bet payouts BEFORE the disclosed house-edge scale:
BACC_W = {"player": 0.4462466093, "banker": 0.4585974226, "tie": 0.0951559680}
BACC_M = {"player": 2.0, "banker": 1.95, "tie": 9.0}          # total return multiple on a win (stake included)

def bacc_val(card):
    r = (card % 13) + 1
    return r if r < 10 else 0

def _banker_draws(b, p3):
    if b <= 2: return True
    if b == 7: return False
    if p3 is None: return b <= 5
    return {3: p3 != 8, 4: 2 <= p3 <= 7, 5: 4 <= p3 <= 7, 6: 6 <= p3 <= 7}[b]

def bacc_deal(rng):
    """Deal one coup from a fresh 8-deck shoe. rng needs .sample(). Returns dict with both hands and the winner."""
    cards = [i % 52 for i in rng.sample(range(416), 6)]
    p = [cards[0], cards[2]]; b = [cards[1], cards[3]]; nxt = 4
    pt = sum(bacc_val(c) for c in p) % 10; bt = sum(bacc_val(c) for c in b) % 10
    if pt < 8 and bt < 8:
        p3 = None
        if pt <= 5:
            p.append(cards[nxt]); nxt += 1; p3 = bacc_val(p[2])
        if _banker_draws(bt, p3):
            b.append(cards[nxt]); nxt += 1
    pt = sum(bacc_val(c) for c in p) % 10; bt = sum(bacc_val(c) for c in b) % 10
    winner = "player" if pt > bt else "banker" if bt > pt else "tie"
    return {"player": p, "banker": b, "player_total": pt, "banker_total": bt, "winner": winner}

def bacc_scale(choice, target_rtp, is_push):
    """Scale applied to the nominal win payout so EVERY bet has RTP == target. A tie when you bet player/banker is a
    push: the stake is returned untouched (scale 1)."""
    if is_push: return 1.0
    w, m = BACC_W[choice], BACC_M[choice]
    t = BACC_W["tie"] if choice != "tie" else 0.0
    return max(0.0, (target_rtp - t) / (w * m))

# ---------------------------------------------------------------- Dragon Tiger (8 decks, one card each, Ace low)
# P(tie) = 13 * (32*31) / (416*415); dragon and tiger share the rest equally. Nominal payouts: 1:1 and tie 8:1.
_DT_TIE = 13 * (32 * 31) / (416 * 415)
DT_W = {"dragon": (1 - _DT_TIE) / 2, "tiger": (1 - _DT_TIE) / 2, "tie": _DT_TIE}
DT_M = {"dragon": 2.0, "tiger": 2.0, "tie": 9.0}

def dt_deal(rng):
    a, b = [i % 52 for i in rng.sample(range(416), 2)]
    ra, rb = (a % 13) + 1, (b % 13) + 1
    return {"dragon": a, "tiger": b, "dragon_rank": ra, "tiger_rank": rb, "winner": "dragon" if ra > rb else "tiger" if rb > ra else "tie"}

def dt_scale(choice, target_rtp, is_push):
    """Every bet lands on exactly target RTP; a tie on a dragon/tiger bet is a push (stake returned untouched)."""
    if is_push: return 1.0
    t = DT_W["tie"] if choice != "tie" else 0.0
    return max(0.0, (target_rtp - t) / (DT_W[choice] * DT_M[choice]))

# ---------------------------------------------------------------- Andar Bahar (single deck, Andar is dealt first)
def _ab_probs():
    from math import comb
    tot = comb(51, 3); andar = sum(comb(51 - k, 2) for k in range(1, 52, 2) if 51 - k >= 2) / tot
    return {"andar": andar, "bahar": 1.0 - andar}
AB_W = _ab_probs()
AB_M = {"andar": 1.0 / AB_W["andar"], "bahar": 1.0 / AB_W["bahar"]}   # fair odds; the disclosed edge is applied on top

def ab_deal(rng):
    deck = list(range(52)); rng.shuffle(deck)
    joker = deck[0]; jr = joker % 13; andar, bahar = [], []
    for i, c in enumerate(deck[1:]):
        (andar if i % 2 == 0 else bahar).append(c)
        if c % 13 == jr:
            return {"joker": joker, "andar": andar, "bahar": bahar, "winner": "andar" if i % 2 == 0 else "bahar"}
    raise RuntimeError("unreachable: a matching rank always exists in 52 cards")

def ab_scale(choice, target_rtp):
    return max(0.0, target_rtp / (AB_W[choice] * AB_M[choice]))

# ---------------------------------------------------------------- Blackjack (6 decks, S17, 3:2, no split)
BJ_DECKS = 6
BJ_NOMINAL_WIN = 2.0      # total return on a win (stake included)
BJ_NOMINAL_BJ = 2.5       # natural blackjack 3:2

def bj_shoe(server_seed, client_seed=""):
    """Deterministic, verifiable shuffle: anyone can recompute it from the revealed server seed + their client seed."""
    h = hashlib.sha256(f"{server_seed}:{client_seed}:blackjack".encode()).digest()
    rng = random.Random(int.from_bytes(h, "big"))
    shoe = [i % 52 for i in range(52 * BJ_DECKS)]
    rng.shuffle(shoe)
    return shoe

def bj_card_val(card):
    r = (card % 13) + 1
    return 11 if r == 1 else min(r, 10)

def bj_value(cards):
    total = sum(bj_card_val(c) for c in cards); aces = sum(1 for c in cards if (c % 13) == 0)
    while total > 21 and aces: total -= 10; aces -= 1
    return total

def bj_is_blackjack(cards): return len(cards) == 2 and bj_value(cards) == 21

def bj_dealer_play(shoe, pos, dealer):
    """Dealer draws to 17 and stands on ALL 17s (including soft 17). Returns (dealer_cards, new_pos)."""
    dealer = list(dealer)
    while bj_value(dealer) < 17:
        dealer.append(shoe[pos]); pos += 1
    return dealer, pos

def bj_result(player, dealer, doubled=False):
    """'blackjack' | 'win' | 'push' | 'lose'"""
    pv, dv = bj_value(player), bj_value(dealer)
    if bj_is_blackjack(player) and not doubled:
        return "push" if bj_is_blackjack(dealer) else "blackjack"
    if pv > 21: return "lose"
    if bj_is_blackjack(dealer): return "lose"
    if dv > 21 or pv > dv: return "win"
    return "push" if pv == dv else "lose"

def bj_payout(total_stake, result, edge):
    """Disclosed payouts: win 2x*(1-edge), blackjack 2.5x*(1-edge), push = stake back (no edge on a push)."""
    k = 1.0 - float(edge)
    if result == "win": return round(total_stake * BJ_NOMINAL_WIN * k, 2)
    if result == "blackjack": return round(total_stake * BJ_NOMINAL_BJ * k, 2)
    if result == "push": return round(float(total_stake), 2)
    return 0.0

def bj_basic_action(player, dealer_up, can_double):
    """Basic strategy (no split) -- used only by tests to estimate RTP."""
    pv = bj_value(player); soft = any((c % 13) == 0 for c in player) and sum(bj_card_val(c) for c in player) <= 21 and pv != sum(min((c % 13) + 1, 10) for c in player)
    up = bj_card_val(dealer_up)
    if soft:
        if pv >= 19: return "stand"
        if pv == 18: return "double" if (can_double and 3 <= up <= 6) else ("stand" if up <= 8 else "hit")
        if pv in (15, 16, 17) and can_double and 4 <= up <= 6: return "double"
        if pv in (13, 14) and can_double and 5 <= up <= 6: return "double"
        return "hit"
    if pv >= 17: return "stand"
    if pv >= 13: return "stand" if up <= 6 else "hit"
    if pv == 12: return "stand" if 4 <= up <= 6 else "hit"
    if pv == 11: return "double" if can_double else "hit"
    if pv == 10: return "double" if (can_double and up <= 9) else "hit"
    if pv == 9: return "double" if (can_double and 3 <= up <= 6) else "hit"
    return "hit"
