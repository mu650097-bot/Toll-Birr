"""Play-only BONUS wallet (shared by the API process and the bot process; both use the same SQLite file).

* `users.bonus_locked` = part of `users.balance` that came from a bonus. It can be PLAYED but not WITHDRAWN.
* Everything that is won with it (balance above the locked amount) is a normal, withdrawable balance.
* A SQLite trigger (see extended_schema.py) lowers bonus_locked whenever balance falls below it, so every game /
  stake path is covered without touching each game's code: real money is spent first, the bonus last.
"""
import os

INVITE_BONUS_ETB = float(os.getenv("INVITE_BONUS_ETB", "1"))          # per invited person (10 people = 10 ETB)


def locked_bonus(cur, uid):
    try:
        cur.execute("SELECT COALESCE(bonus_locked,0) FROM users WHERE user_id=?", (uid,))
        r = cur.fetchone()
        return float(r[0] or 0) if r else 0.0
    except Exception:           # column not created yet (very old DB)
        return 0.0


def withdrawable(cur, uid):
    """(balance, locked_bonus, withdrawable_amount)"""
    cur.execute("SELECT COALESCE(balance,0) FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    bal = float(r[0] or 0) if r else 0.0
    lk = min(locked_bonus(cur, uid), bal)
    return bal, lk, max(0.0, round(bal - lk, 2))


def grant_locked_bonus(cur, uid, amount, ttype, now):
    """Add a play-only bonus. Caller owns the transaction (commit / rollback)."""
    amount = round(float(amount), 2)
    if amount <= 0:
        return False
    cur.execute("UPDATE users SET balance=COALESCE(balance,0)+?, bonus_locked=COALESCE(bonus_locked,0)+? WHERE user_id=?",
                (amount, amount, uid))
    if cur.rowcount != 1:
        return False
    cur.execute("INSERT INTO transactions(user_id,amount,transaction_type,created_at) VALUES(?,?,?,?)", (uid, amount, ttype, now))
    return True


def _setting(cur, key, default):
    try:
        cur.execute("SELECT value FROM platform_settings WHERE key=?", (key,))
        r = cur.fetchone()
        return r[0] if r else default
    except Exception:
        return default


def invite_requires_deposit(cur):
    """True (default) = the inviter is paid only after the INVITED person's first qualifying deposit."""
    return str(_setting(cur, "invite_bonus_requires_deposit", "1")) == "1"


def record_invite(cur, inviter, invitee, now):
    """Link invitee -> inviter once. Caller commits. Returns True when the invite was counted.
    With invite_bonus_requires_deposit=1 (default) nothing is paid yet: the row stays unpaid (paid_at NULL) until
    release_invite_bonus() runs after the invitee's first approved deposit. Otherwise it is paid immediately."""
    if not inviter or inviter == invitee:
        return False
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (inviter,))
    if not cur.fetchone():
        return False
    cur.execute("UPDATE users SET referred_by=? WHERE user_id=? AND referred_by IS NULL", (inviter, invitee))
    if cur.rowcount != 1:
        return False
    deferred = invite_requires_deposit(cur)
    cur.execute("INSERT OR IGNORE INTO invite_bonuses(invitee_id,inviter_id,amount,created_at,paid_at) VALUES(?,?,?,?,?)",
                (invitee, inviter, INVITE_BONUS_ETB, now, None if deferred else now))
    if cur.rowcount == 1 and not deferred and INVITE_BONUS_ETB > 0:
        grant_locked_bonus(cur, inviter, INVITE_BONUS_ETB, "invite_bonus", now)
    return True


def release_invite_bonus(cur, invitee, deposit_amount, now):
    """Call inside the deposit-approval transaction (caller commits). Pays the inviter once, when the invitee's
    deposit reaches invite_bonus_min_deposit. Returns (inviter_id, amount) when paid, else None."""
    if not invite_requires_deposit(cur):
        return None
    try:
        min_dep = float(_setting(cur, "invite_bonus_min_deposit", "10"))
    except (TypeError, ValueError):
        min_dep = 10.0
    if float(deposit_amount) < min_dep:
        return None
    cur.execute("SELECT inviter_id,amount FROM invite_bonuses WHERE invitee_id=? AND paid_at IS NULL", (invitee,))
    r = cur.fetchone()
    if not r:
        return None
    inviter, amount = int(r[0]), float(r[1] or 0)
    cur.execute("UPDATE invite_bonuses SET paid_at=? WHERE invitee_id=? AND paid_at IS NULL", (now, invitee))
    if cur.rowcount != 1:
        return None
    if amount > 0 and grant_locked_bonus(cur, inviter, amount, "invite_bonus", now):
        return inviter, amount
    return None
