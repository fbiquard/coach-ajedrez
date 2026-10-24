"""Diagnóstico por ritmo (blitz / rapid) a partir de los informes de partidas."""
import collections
import time

CLOCK = {
    "blitz": [(">2 min", 120, 1e9), ("1-2 min", 60, 120), ("30-60s", 30, 60), ("<30s", 0, 30)],
    "rapid": [(">5 min", 300, 1e9), ("2-5 min", 120, 300), ("1-2 min", 60, 120), ("<1 min", 0, 60)],
}
SPENT = {
    "blitz": [("<2s", 0, 2), ("2-5s", 2, 5), ("5-15s", 5, 15), (">15s", 15, 1e9)],
    "rapid": [("<5s", 0, 5), ("5-15s", 5, 15), ("15-45s", 15, 45), (">45s", 45, 1e9)],
}


def _bucket(v, spec):
    for name, lo, hi in spec:
        if lo <= v < hi:
            return name
    return spec[-1][0]


def _rate(rows):
    return [dict(label=k, moves=n, blunders=b, rate=round(100 * b / n, 2) if n else 0) for k, n, b in rows]


def for_class(reports, tc, last_n=300):
    games = sorted([r for r in reports if r["time_class"] == tc], key=lambda r: r["date"])[-last_n:]
    if not games:
        return None
    moves = [m for r in games for m in r["moves"]]
    errs = [e for r in games for e in r["errors"]]
    blunders = [e for e in errs if e["sev"] == "blunder"]
    res = collections.Counter(r["outcome"] for r in games)

    phase_rows = []
    for ph in ("apertura", "medio juego", "final"):
        phase_rows.append((ph, sum(m["phase"] == ph for m in moves), sum(e["phase"] == ph for e in blunders)))

    spec = CLOCK.get(tc, CLOCK["rapid"])
    clk = collections.OrderedDict((name, [0, 0]) for name, _, _ in spec)
    for m in moves:
        if m["clk"] is None:
            continue
        k = _bucket(m["clk"], spec)
        clk[k][0] += 1
        clk[k][1] += m["loss"] >= 30

    sspec = SPENT.get(tc, SPENT["rapid"])
    sp = collections.OrderedDict((name, [0, 0]) for name, _, _ in sspec)
    for m in moves:
        if m["spent"] is None or m["move_no"] <= 8:
            continue
        k = _bucket(m["spent"], sspec)
        sp[k][0] += 1
        sp[k][1] += m["loss"] >= 30

    kinds = collections.Counter(e["label"] for e in blunders).most_common()
    won_pos = [r for r in games if r["max_wp"] >= 85]

    now = time.time()
    recent = [r for r in games if r["date"] >= now - 30 * 86400]
    older = [r for r in games if r["date"] < now - 30 * 86400]
    bpg = lambda gs: round(sum(r["n_blunders"] for r in gs) / len(gs), 2) if gs else None

    spent_all = sorted(m["spent"] for m in moves if m["spent"] is not None and m["move_no"] > 8)
    op = collections.defaultdict(lambda: [0, 0, 0])
    for r in games:
        k = (r["color"], r["opening"])
        op[k][0] += 1
        op[k][1] += r["outcome"] == "W"
        op[k][2] += r["outcome"] == "D"
    openings = sorted([dict(color=c, name=n, n=v[0], pct=round(100 * (v[1] + 0.5 * v[2]) / v[0]))
                       for (c, n), v in op.items() if v[0] >= 5], key=lambda x: -x["n"])[:12]

    return dict(
        time_class=tc, n_games=len(games), first=games[0]["date"], last=games[-1]["date"],
        results=dict(W=res.get("W", 0), D=res.get("D", 0), L=res.get("L", 0)),
        rating=[[r["date"], r["rating"]] for r in games],
        n_blunders=len(blunders), blunders_per_game=round(len(blunders) / len(games), 2),
        bpg_recent=bpg(recent), bpg_older=bpg(older), n_recent=len(recent),
        phase=_rate(phase_rows), clock=_rate([(k, v[0], v[1]) for k, v in clk.items()]),
        spent=_rate([(k, v[0], v[1]) for k, v in sp.items()]),
        median_spent=spent_all[len(spent_all) // 2] if spent_all else None,
        kinds=[dict(label=k, n=n) for k, n in kinds],
        conv=dict(n=len(won_pos), won=sum(r["outcome"] == "W" for r in won_pos)),
        missed=sum(1 for e in errs if e["kind"] in ("castigar", "no_aprovechaste")),
        openings=openings)


def build(reports):
    return {tc: s for tc in ("rapid", "blitz") if (s := for_class(reports, tc))}
