"""Convierte una partida evaluada en el informe que muestra la web: errores, momentos clave y puzzles."""
import chess
from chesslib import wp, phase, classify, best_gain, san_line, opening_family, KIND_LABEL

TEXT = {
    "colgaste_movida": "Jugaste {p} y esa misma pieza quedó colgada: {r1} y se lleva tu {pc}.",
    "colgaste_otra": "Con {p} dejaste tu {pc} sin defensa. El rival tenía {r1}.",
    "horquilla": "Después de {p} el rival tiene {r1}, un ataque doble que gana material.",
    "tactica_jaque": "{p} permite {r1} con jaque, y la secuencia termina ganando material.",
    "tactica": "{p} pierde material. La refutación: {rl}.",
    "mate": "{p} permite mate. Línea del motor: {rl}.",
    "no_aprovechaste": "El rival te había dejado algo: {b} ganaba material y jugaste {p}.",
    "posicional": "{p} no regala material enseguida, pero tira la ventaja. Lo correcto era {b}.",
    "castigar": "El rival acababa de equivocarse y {b} lo castigaba. Jugaste {p}.",
    "otro": "{p} empeora mucho la posición. Lo correcto era {b}.",
}
QUESTION = {
    "no_aprovechaste": "El rival acaba de equivocarse. ¿Cómo lo castigás?",
    "castigar": "El rival acaba de equivocarse. ¿Cómo lo castigás?",
    "mate": "Cuidado: hay una amenaza. ¿Qué jugás?",
}
DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
LOSS_RESULTS = {"resigned", "checkmated", "timeout", "abandoned", "lose"}


def outcome(result):
    if result == "win":
        return "W"
    if result in DRAW_RESULTS:
        return "D"
    return "L"


def build(meta, plies, user="fbiquard"):
    me = chess.WHITE if meta["color"] == "white" else chess.BLACK
    sign = 1 if me == chess.WHITE else -1
    base, inc = (meta["tc"].split("+") + ["0"])[:2]
    base = int(base) if base.isdigit() else 0
    inc = int(inc) if inc.isdigit() else 0
    curve, moves, errors, opp_errors = [], [], [], []
    prev_clk = base
    for i, p in enumerate(plies):
        b = chess.Board(p["fen"])
        wb, wa = wp(sign * p["eval_before"]), wp(sign * p["eval_after"])
        curve.append(round(wa, 1))
        if b.turn != me:
            if wa - wb >= 20:
                opp_errors.append(dict(ply=i, move_no=b.fullmove_number, san=p["san"], gain=round(wa - wb)))
            continue
        clk = p["clk"]
        spent = None
        if clk is not None and base:
            spent = max(0, prev_clk - clk + inc)
            prev_clk = clk
        loss = max(0, wb - wa)
        ph = phase(b)
        moves.append(dict(ply=i, move_no=b.fullmove_number, phase=ph, clk=clk, spent=spent,
                          wb=round(wb, 1), wa=round(wa, 1), loss=round(loss, 1)))
        if loss < 20:
            continue
        reply_pv = plies[i + 1]["pv"] if i + 1 < len(plies) else []
        prev_opp_gift = i >= 1 and (wp(-sign * plies[i - 1]["eval_before"]) - wp(-sign * plies[i - 1]["eval_after"])) >= 25
        if p["eval_after"] * sign <= -9000:
            kind, piece = "mate", None
        else:
            kind, piece = classify(b, p["move"], reply_pv, me)
            if kind == "posicional" and best_gain(b, p["pv"], me) >= 2:
                kind = "no_aprovechaste"
        if prev_opp_gift and kind in ("posicional", "no_aprovechaste", "otro") and wb >= 60:
            kind = "castigar"
        b2 = b.copy()
        b2.push(chess.Move.from_uci(p["move"]))
        played = san_line(p["fen"], [p["move"]], 1)
        best = san_line(p["fen"], [p["best"]], 1) if p["best"] else "?"
        r1 = san_line(b2.fen(), reply_pv, 1) if reply_pv else ""
        nag = "??" if loss >= 30 else "?"
        errors.append(dict(
            ply=i, move_no=b.fullmove_number, phase=ph, clk=clk, spent=spent, kind=kind,
            label=KIND_LABEL[kind], sev="blunder" if loss >= 30 else "mistake",
            wb=round(wb), wa=round(wa), loss=round(loss), fen=p["fen"], played=played,
            played_uci=p["move"], best=best, best_uci=p["best"], best_line=san_line(p["fen"], p["pv"], 5),
            refutation=san_line(b2.fen(), reply_pv, 5),
            text=TEXT[kind].format(p=played + nag, r1=r1, pc=piece or "pieza",
                                   rl=san_line(b2.fen(), reply_pv, 4), b=best).replace("?.", "?")))
    # Puzzles: errores en posiciones que no estaban perdidas, hasta 3 por partida
    cands = [e for e in errors if e["wb"] >= 35 and e["best_uci"]]
    cands.sort(key=lambda e: -e["loss"])
    puzzles = []
    for e in cands[:3]:
        puzzles.append(dict(
            id=f'{meta["uuid"][:8]}-{e["ply"]}', fen=e["fen"], kind=e["kind"], label=e["label"],
            question=QUESTION.get(e["kind"], "Te toca. ¿Qué jugás?"), solution=[e["best_uci"]],
            solution_san=e["best"], line=e["best_line"], played=e["played"], played_uci=e["played_uci"],
            text=e["text"], wb=e["wb"], wa=e["wa"], move_no=e["move_no"], phase=e["phase"]))
    my_res = meta["result"]
    max_wp = max([m["wb"] for m in moves], default=50)
    return dict(
        id=meta["uuid"], url=meta["url"], date=meta["end"], time_class=meta["time_class"], tc=meta["tc"],
        color=meta["color"], rating=meta["my_rating"], opp=meta.get("opp_name", ""),
        opp_rating=meta["opp_rating"], result=my_res, outcome=outcome(my_res),
        opening=opening_family(meta.get("eco", "")), accuracy=(meta.get("accuracies") or {}).get(meta["color"]),
        n_moves=len(moves), n_blunders=sum(e["sev"] == "blunder" for e in errors),
        n_mistakes=sum(e["sev"] == "mistake" for e in errors), max_wp=round(max_wp),
        blown=max_wp >= 85 and outcome(my_res) != "W",
        opp_errors=opp_errors, errors=errors, puzzles=puzzles, curve=curve, moves=moves, base=base,
        advice=None)
