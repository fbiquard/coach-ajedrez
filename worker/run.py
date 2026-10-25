"""Corre en el cron: baja partidas nuevas de chess.com, las analiza y regenera los datos de la web.

Variables de entorno:
  CHESS_USER        usuario de chess.com (default fbiquard)
  MAX_GAMES         partidas nuevas a analizar por corrida (default 25)
  THINK             segundos de Stockfish por jugada (default 0.15)
  MONTHS            meses hacia atrás a revisar (default 2)
  ADVICE_BACKFILL   partidas recientes con consejo de plantilla a reescribir con Claude por corrida (default 10)
  ANTHROPIC_API_KEY opcional: si está, los consejos los escribe Claude
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import advice  # noqa: E402
import best  # noqa: E402
import game_report  # noqa: E402
import plan  # noqa: E402
import stats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "data" / "evals"
REPORTS = ROOT / "data" / "reports"
SITE = ROOT / "site" / "data"
USER = os.environ.get("CHESS_USER", "fbiquard")
TIME_CLASSES = ("rapid", "blitz")
UA = {"User-Agent": f"coach-ajedrez/1.0 (personal app for {USER})"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def meta_from_game(g):
    me = "white" if g["white"]["username"].lower() == USER.lower() else "black"
    op = "black" if me == "white" else "white"
    return dict(uuid=g["uuid"], url=g["url"], time_class=g["time_class"], tc=g["time_control"],
                end=g["end_time"], color=me, my_rating=g[me]["rating"], opp_rating=g[op]["rating"],
                opp_name=g[op]["username"], result=g[me]["result"], opp_result=g[op]["result"],
                eco=g.get("eco", ""), accuracies=g.get("accuracies"))


def strip(report):
    """Versión liviana para la web (sin el detalle jugada por jugada)."""
    return {k: v for k, v in report.items() if k != "moves"}


def summary(r):
    keys = ["id", "url", "date", "time_class", "tc", "color", "rating", "opp", "opp_rating", "result",
            "outcome", "opening", "accuracy", "n_blunders", "n_mistakes", "blown", "max_wp"]
    s = {k: r[k] for k in keys}
    s["n_puzzles"] = len(r["puzzles"])
    s["advice"] = (r.get("advice") or {}).get("text", "")
    return s


def fetch_new(processed, months):
    archives = get_json(f"https://api.chess.com/pub/player/{USER}/games/archives")["archives"][-months:]
    new = []
    for url in archives:
        for g in get_json(url).get("games", []):
            if g.get("rules") == "chess" and g.get("time_class") in TIME_CLASSES and g["uuid"] not in processed:
                new.append(g)
        time.sleep(0.5)
    return sorted(new, key=lambda g: g["end_time"])


def process(g, engine):
    meta = meta_from_game(g)
    plies = engine.analyse_game(g["pgn"])
    (EVALS / f"{meta['uuid']}.json").write_text(json.dumps(dict(meta=meta, plies=plies), separators=(",", ":")))
    return finish(meta, plies, engine)


def finish(meta, plies, engine=None):
    r = game_report.build(meta, plies, USER)
    if engine:
        for p in r["puzzles"]:
            ok, line = engine.solutions(p["fen"])
            if ok:
                p["solution"] = list(dict.fromkeys([p["solution"][0]] + ok))
    r["advice"] = advice.write(r)
    (REPORTS / f"{r['id']}.json").write_text(json.dumps(r, separators=(",", ":"), ensure_ascii=False))
    return r


def save(r):
    (REPORTS / f"{r['id']}.json").write_text(json.dumps(r, separators=(",", ":"), ensure_ascii=False))


def update_best(engine_factory, limit):
    """Busca jugadas destacadas en las candidatas a mejores partidas y explica las que entran al top."""
    reports = [json.loads(f.read_text()) for f in REPORTS.glob("*.json")]
    eng = None
    done = 0
    for tc in ("rapid", "blitz"):
        pool = [r for r in reports if r["time_class"] == tc and best.base_score(r) is not None]
        pool.sort(key=lambda r: -best.base_score(r))
        for r in pool[:best.CANDIDATES]:
            if r.get("hl_done") or done >= limit:
                continue
            ev = EVALS / f"{r['id']}.json"
            if not ev.exists():
                continue
            if eng is None:
                eng = engine_factory()
            r["highlights"] = best.find_highlights(r, json.loads(ev.read_text())["plies"], eng)
            r["hl_done"] = True
            save(r)
            done += 1
    if eng:
        eng.close()
    # explicaciones para el top de cada ritmo
    reports = [json.loads(f.read_text()) for f in REPORTS.glob("*.json")]
    n_exp = 0
    for tc in ("rapid", "blitz"):
        pool = [r for r in reports if r["time_class"] == tc]
        losses = [best.avg_loss(r) for r in pool if r.get("moves")]
        median_loss = sorted(losses)[len(losses) // 2] if losses else 3
        ranked = sorted([r for r in pool if best.score(r) is not None and r.get("hl_done")],
                        key=lambda r: -best.score(r))[:best.TOP]
        for r in ranked:
            want_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
            cur = r.get("best_why") or {}
            if cur and (cur.get("source") == "claude" or not want_claude):
                continue
            r["best_why"] = best.explain(r, median_loss)
            save(r)
            n_exp += 1
    return done, n_exp


def best_list(reports):
    out = {}
    for tc in ("rapid", "blitz"):
        pool = [r for r in reports if r["time_class"] == tc]
        losses = [best.avg_loss(r) for r in pool if r.get("moves")]
        median_loss = sorted(losses)[len(losses) // 2] if losses else 3
        ranked = sorted([r for r in pool if best.score(r) is not None and r.get("hl_done")],
                        key=lambda r: -best.score(r))[:best.TOP]
        out[tc] = [dict(summary(r), score=best.score(r), why=(r.get("best_why") or {}).get("text", ""),
                        why_source=(r.get("best_why") or {}).get("source", ""),
                        tags=best.tags(r, median_loss),
                        highlights=[{k: h[k] for k in ("type", "move_no", "san", "uci", "fen", "line", "wb", "second")}
                                    for h in r.get("highlights") or []][:3])
                   for r in ranked]
    return out


def rebuild_site():
    reports = [json.loads(f.read_text()) for f in REPORTS.glob("*.json")]
    reports.sort(key=lambda r: -r["date"])
    (SITE / "games").mkdir(parents=True, exist_ok=True)
    for r in reports:
        (SITE / "games" / f"{r['id']}.json").write_text(json.dumps(strip(r), separators=(",", ":"), ensure_ascii=False))
    puzzles = []
    for r in reports:
        for p in r["puzzles"]:
            puzzles.append(dict(p, game=r["id"], date=r["date"], time_class=r["time_class"], color=r["color"],
                                url=r["url"], opp=r["opp"]))
    index = dict(user=USER, updated=int(time.time()), games=[summary(r) for r in reports],
                 stats=stats.build(reports), best=best_list(reports), plan=plan.build(reports))
    (SITE / "index.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False))
    (SITE / "puzzles.json").write_text(json.dumps(puzzles, separators=(",", ":"), ensure_ascii=False))
    return len(reports), len(puzzles)


def backfill_advice(limit):
    if not os.environ.get("ANTHROPIC_API_KEY") or limit <= 0:
        return 0
    files = sorted(REPORTS.glob("*.json"), key=lambda f: -json.loads(f.read_text())["date"])[:30]
    done = 0
    for f in files:
        r = json.loads(f.read_text())
        if (r.get("advice") or {}).get("source") == "claude":
            continue
        r["advice"] = advice.write(r)
        f.write_text(json.dumps(r, separators=(",", ":"), ensure_ascii=False))
        done += 1
        if done >= limit:
            break
    return done


def main():
    for d in (EVALS, REPORTS, SITE):
        d.mkdir(parents=True, exist_ok=True)
    processed = {f.stem for f in REPORTS.glob("*.json")}
    new = fetch_new(processed, int(os.environ.get("MONTHS", "2")))
    max_games = int(os.environ.get("MAX_GAMES", "25"))
    print(f"{len(new)} partidas nuevas; analizo hasta {max_games}")
    if new:
        from engine import Engine
        eng = Engine(float(os.environ.get("THINK", "0.15")))
        try:
            for g in new[-max_games:]:
                r = process(g, eng)
                print("ok", r["date"], r["time_class"], r["outcome"], r["n_blunders"], "blunders")
        finally:
            eng.close()
    n_adv = backfill_advice(int(os.environ.get("ADVICE_BACKFILL", "10")))

    def make_engine():
        from engine import Engine
        return Engine(float(os.environ.get("THINK", "0.15")))
    n_hl, n_exp = update_best(make_engine, int(os.environ.get("BEST_BACKFILL", "15")))
    n, np_ = rebuild_site()
    print("Claude:", "con API key" if os.environ.get("ANTHROPIC_API_KEY") else "SIN API key (consejos de plantilla)")
    print(f"web: {n} partidas, {np_} puzzles, {n_adv} consejos reescritos con Claude, "
          f"{n_hl} partidas revisadas para mejores, {n_exp} explicaciones")


if __name__ == "__main__":
    main()
