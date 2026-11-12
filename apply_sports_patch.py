#!/usr/bin/env python3
"""Adds optional `league` and `sport` (football | basketball | tennis) to Sports matches.

Usage:  python apply_sports_patch.py /path/to/project          (project dir holds webapp_api.py, extended_schema.py, app.js)
        python apply_sports_patch.py /path/to/project --check   (only report whether every anchor is found)

Safe by design: every edit is an exact-text replacement that must match EXACTLY ONCE. If any anchor is missing or ambiguous in any file,
NOTHING is written and the script says which anchor failed. A .bak copy of each file is made before writing. Re-running is harmless.
What it changes (backwards compatible; existing matches keep working, they are simply "football" without a league):
  extended_schema.py : two new nullable columns league, sport on sports_matches
  webapp_api.py      : /api/sports/matches also returns league + sport; admin "create match" accepts league + sport;
                       two-way sports (basketball, tennis) take no draw odds (stored as 0, so a DRAW bet is refused as "odds unavailable")
  app.js             : admin "new match" form gets a Sport select + League field (Draw odds hide for two-way sports)
It does NOT enable betting after kickoff (see README).
"""
import os, shutil, sys

EDITS = {
 "extended_schema.py": [
  ("    add_col('sports_matches', 'live_updated_at', 'TEXT')\n",
   "    add_col('sports_matches', 'live_updated_at', 'TEXT')\n    add_col('sports_matches', 'league', 'TEXT')\n    add_col('sports_matches', 'sport', 'TEXT')\n"),
 ],
 "webapp_api.py": [
  ('"SELECT id, home_team, away_team, odds_home, odds_draw, odds_away, closes_at, home_score, away_score, live_minute "',
   '"SELECT id, home_team, away_team, odds_home, odds_draw, odds_away, closes_at, home_score, away_score, live_minute, league, sport "'),
  ('        od=parse_money(body.get("odds_draw"),"odds_draw")\n        oa=parse_money(body.get("odds_away"),"odds_away")\n',
   '        sport=str(body.get("sport") or "football").strip().lower()\n'
   '        league=(str(body.get("league") or "").strip()[:40]) or None\n'
   '        od=parse_money(body.get("odds_draw"),"odds_draw") if sport=="football" else 0.0   # basketball/tennis: two-way, no draw\n'
   '        oa=parse_money(body.get("odds_away"),"odds_away")\n'),
  ('    if not home or not away or home==away or min(oh,od,oa)<=1.0 or max(oh,od,oa)>1000:\n',
   '    if sport not in ("football","basketball","tennis"):\n        return jsonify({"error":"invalid sport"}),400\n'
   '    odds_all=[x for x in ((oh,od,oa) if sport=="football" else (oh,oa))]\n'
   '    if not home or not away or home==away or min(odds_all)<=1.0 or max(odds_all)>1000:\n'),
  ('    overround = 1.0/oh + 1.0/od + 1.0/oa\n', '    overround = sum(1.0/x for x in odds_all)\n'),
  ("INSERT INTO sports_matches(home_team,away_team,odds_home,odds_draw,odds_away,status,created_at,closes_at) VALUES(?,?,?,?,?,'OPEN',?,?)\",(home,away,oh,od,oa,_now(),closes_at))",
   "INSERT INTO sports_matches(home_team,away_team,odds_home,odds_draw,odds_away,status,created_at,closes_at,league,sport) VALUES(?,?,?,?,?,'OPEN',?,?,?,?)\",(home,away,oh,od,oa,_now(),closes_at,league,sport))"),
 ],
 "app.js": [
  ('        <label>Home team</label><input id="spf-home"',
   '        <div class="sp-odds"><div><label>Sport</label><select id="spf-sport"><option value="football">⚽ Football</option><option value="basketball">🏀 Basketball</option><option value="tennis">🎾 Tennis</option></select></div>'
   '<div><label>League</label><input id="spf-league" type="text" maxlength="40" autocomplete="off" placeholder="Premier League"></div></div>\n'
   '        <label>Home team</label><input id="spf-home"'),
  ('        const m = 1 / oh + 1 / od + 1 / oa;\n',
   '        const two = $("spf-sport") && $("spf-sport").value !== "football"; const m = 1 / oh + (two ? 0 : 1 / od) + 1 / oa;\n'),
  ('["spf-oh", "spf-od", "spf-oa"].forEach((id) => $(id).addEventListener("input", margin)); margin();',
   '["spf-oh", "spf-od", "spf-oa"].forEach((id) => $(id).addEventListener("input", margin)); margin();\n'
   '      $("spf-sport").addEventListener("change", () => { $("spf-od").parentElement.style.display = $("spf-sport").value === "football" ? "" : "none"; margin(); });'),
  ('odds_draw: parseFloat($("spf-od").value), odds_away: parseFloat($("spf-oa").value), closes_at }',
   'odds_draw: $("spf-sport").value === "football" ? parseFloat($("spf-od").value) : undefined, odds_away: parseFloat($("spf-oa").value), closes_at, sport: $("spf-sport").value, league: $("spf-league").value.trim() }'),
 ],
}
MARK = "league, sport "   # presence in webapp_api.py means already patched


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    root = args[0]; new = {}; problems = []
    for fn, edits in EDITS.items():
        p = os.path.join(root, fn)
        if not os.path.exists(p):
            problems.append(f"{fn}: file not found in {root}"); continue
        s = open(p, encoding="utf-8").read(); orig = s
        for i, (old, rep) in enumerate(edits, 1):
            if rep in s:
                continue                                   # already applied (rep may contain old, so test rep first)
            n = s.count(old)
            if n != 1:
                problems.append(f"{fn}: edit #{i} anchor found {n} times (need exactly 1): {old[:70]!r}"); continue
            s = s.replace(old, rep)
        if s != orig: new[fn] = s
    if problems:
        print("NOTHING WRITTEN. Problems:"); [print(" -", x) for x in problems]; sys.exit(1)
    if check:
        print("CHECK OK: all anchors found;", "would change " + ", ".join(new) if new else "already patched"); return
    for fn, s in new.items():
        p = os.path.join(root, fn); shutil.copyfile(p, p + ".bak"); open(p, "w", encoding="utf-8").write(s)
    print("patched:", ", ".join(new) if new else "nothing to do (already patched)")


if __name__ == "__main__":
    main()
