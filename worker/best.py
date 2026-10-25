"""Mejores partidas: puntaje, jugadas destacadas (únicas y sacrificios) y explicación de por qué."""
import json
import os
import statistics

import chess

from chesslib import wp, material, san_line, VAL

MIN_MOVES = 18          # jugadas propias mínimas para considerar una partida
CANDIDATES = 40         # partidas por ritmo a las que se les buscan jugadas destacadas
TOP = 12                # mejores partidas por ritmo que muestra la web


# ---------- puntaje ----------
def avg_loss(r):
    ms = r.get("moves") or []
    return statistics.mean(m["loss"] for m in ms) if ms else 99


def base_score(r):
    """Puntaje sin jugadas destacadas: precisión, rival, errores y largo."""
    if r["outcome"] == "L" or len(r.get("moves") or []) < MIN_MOVES:
        return None
    diff = r["opp_rating"] - r["rating"]
    if r["outcome"] == "D" and diff < 100:
        return None
    s = 50 - 12 * avg_loss(r)
    s += max(-300, min(250, diff)) / 8
    s -= 12 * r["n_blunders"] + 4 * r["n_mistakes"]
    s += min(len(r["moves"]), 60) / 6
    if r["outcome"] == "D":
        s -= 10
    return s


def score(r):
    b = base_score(r)
    if b is None:
        return None
    hl = r.get("highlights") or []
    bonus = sum(14 if h["type"] == "sacrificio" else 10 for h in hl)
    return round(b + min(bonus, 40), 1)


# ---------- jugadas destacadas ----------
def is_sacrifice(b, mv):
    """La jugada deja una pieza de valor >=3 en el aire (cambio simple, sin cadenas)."""
    me = b.turn
    moved = b.piece_at(mv.from_square)
    captured = b.piece_at(mv.to_square)
    if b.is_en_passant(mv):
        captured = chess.Piece(chess.PAWN, not me)
    cap_val = VAL[captured.piece_type] if captured else 0
    mv_val = VAL[mv.promotion] if mv.promotion else VAL[moved.piece_type]
    b2 = b.copy()
    b2.push(mv)
    if b2.is_checkmate() or mv_val < 3:
        return False
    caps = [m for m in b2.legal_moves if m.to_square == mv.to_square]
    if not caps:
        return False
    min_att = min(VAL[b2.piece_at(m.from_square).piece_type] or 100 for m in caps)
    if not b2.is_attacked_by(me, mv.to_square):
        loss = mv_val - cap_val
    elif min_att < mv_val:
        loss = mv_val - cap_val - min_att
    else:
        loss = 0
    return loss >= 2


def find_highlights(report, plies, engine, think=0.25):
    """Busca jugadas únicas y sacrificios correctos. Devuelve una lista ordenada por jugada."""
    me = chess.WHITE if report["color"] == "white" else chess.BLACK
    out = []
    for i, p in enumerate(plies):
        b = chess.Board(p["fen"])
        if b.turn != me or b.fullmove_number < 6:
            continue
        sign = 1 if me == chess.WHITE else -1
        wb = wp(sign * p["eval_before"])
        if wb < 12 or wb > 92:
            continue  # posición ya decidida: no hay mérito especial
        mv = chess.Move.from_uci(p["move"])
        sac = is_sacrifice(b, mv)
        # filtro barato: solo analizamos jugadas que coinciden con la del motor o que son sacrificios
        if p["move"] != p["best"] and not sac:
            continue
        # sin mérito: capturas comunes (recapturas, piezas regaladas) y jugadas casi forzadas
        if not sac and (b.is_capture(mv) or (b.is_check() and b.legal_moves.count() <= 3)):
            continue
        lines = engine.multipv(p["fen"], 2, think)
        if not lines:
            continue
        best_uci, best_cp, _ = lines[0]
        second_cp = lines[1][1] if len(lines) > 1 else -10000
        played = next((l for l in lines if l[0] == p["move"]), None)
        mine_cp = played[1] if played else None
        if mine_cp is None:
            continue
        if wp(mine_cp) < wp(best_cp) - 3:
            continue
        gap = wp(best_cp) - wp(second_cp)
        entry = dict(ply=i, move_no=b.fullmove_number, fen=p["fen"], uci=p["move"], san=p["san"],
                     line=san_line(p["fen"], played[2], 5), wb=round(wb), wa=round(wp(mine_cp)),
                     second=round(wp(second_cp)))
        if sac:
            # el material invertido sigue invertido después de la línea del motor
            bb = b.copy()
            mat0 = material(bb, me) - material(bb, not me)
            for m in played[2][:6]:
                mm = chess.Move.from_uci(m)
                if mm not in bb.legal_moves:
                    break
                bb.push(mm)
            if mat0 - (material(bb, me) - material(bb, not me)) >= 2:
                out.append(dict(entry, type="sacrificio"))
                continue
        if p["move"] == best_uci and gap >= 20:
            out.append(dict(entry, type="única"))
    return out


# ---------- explicación ----------
SYSTEM = """Sos el entrenador de ajedrez personal de Fede (fbiquard en chess.com).
Escribís en castellano rioplatense, directo, sin elogios vacíos ni exageraciones.
Te paso los datos de una de sus mejores partidas, ya analizada con Stockfish. Explicá por qué es una de sus mejores:
qué hizo bien, cuál fue la jugada o decisión clave y qué hábito suyo hay que repetir.
No calcules ni inventes jugadas: usá solo las que aparecen en los datos, en notación inglesa (N, B, R, Q, K).
Máximo 3 oraciones, un solo párrafo, sin listas ni títulos."""


def facts(r, median_loss):
    return dict(
        ritmo=r["time_class"], color="blancas" if r["color"] == "white" else "negras",
        resultado={"W": "ganó", "D": "empató"}[r["outcome"]], apertura=r["opening"],
        rating=r["rating"], rating_rival=r["opp_rating"], jugadas=len(r["moves"]),
        perdida_media_por_jugada=round(avg_loss(r), 2), su_perdida_media_habitual=round(median_loss, 2),
        blunders=r["n_blunders"], errores=r["n_mistakes"],
        peor_momento_chances=min(m["wb"] for m in r["moves"]),
        jugadas_destacadas=[{k: h[k] for k in ("type", "move_no", "san", "line", "wb", "second")}
                            for h in r.get("highlights") or []],
    )


def template(r, median_loss):
    parts = []
    hl = r.get("highlights") or []
    sacs = [h for h in hl if h["type"] == "sacrificio"]
    only = [h for h in hl if h["type"] == "única"]
    if sacs:
        h = sacs[0]
        parts.append(f"La clave fue el sacrificio {h['move_no']}{'.' if r['color'] == 'white' else '…'}{h['san']}, que era correcto: la línea sigue {h['line']}.")
    if only:
        h = only[0]
        parts.append(f"En la jugada {h['move_no']} encontraste {h['san']}, la única buena: la segunda mejor te dejaba en {h['second']}% de chances.")
    if r["n_blunders"] == 0 and r["n_mistakes"] == 0:
        parts.append("No cometiste ningún error grave en toda la partida.")
    loss = avg_loss(r)
    if loss < median_loss * 0.6:
        a, m = f"{loss:.1f}".replace(".", ","), f"{median_loss:.1f}".replace(".", ",")
        parts.append(f"Jugaste mucho más preciso que de costumbre: perdiste {a} puntos de chances por jugada contra {m} habitual.")
    if r["opp_rating"] - r["rating"] >= 50:
        parts.append(f"Y contra un rival {r['opp_rating'] - r['rating']} puntos más alto.")
    return " ".join(parts[:3]) or "Partida sólida de principio a fin."


def explain(r, median_loss):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic
            from advice import MODEL
            msg = anthropic.Anthropic(api_key=key).messages.create(
                model=MODEL, max_tokens=2000, system=SYSTEM,
                messages=[{"role": "user", "content": json.dumps(facts(r, median_loss), ensure_ascii=False)}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            if text and msg.stop_reason == "end_turn":
                return dict(text=text, source="claude", v=2)
            print("Claude: respuesta incompleta, uso plantilla:", msg.stop_reason)
        except Exception as exc:
            print("best: falló Claude:", exc)
    return dict(text=template(r, median_loss), source="plantilla")


def tags(r, median_loss):
    t = []
    hl = r.get("highlights") or []
    n_sac = sum(h["type"] == "sacrificio" for h in hl)
    n_only = sum(h["type"] == "única" for h in hl)
    if n_sac:
        t.append("Sacrificio correcto" if n_sac == 1 else f"{n_sac} sacrificios")
    if n_only:
        t.append("Jugada única" if n_only == 1 else f"{n_only} jugadas únicas")
    if r["n_blunders"] == 0 and r["n_mistakes"] == 0:
        t.append("Sin errores")
    if r["opp_rating"] - r["rating"] >= 50:
        t.append(f"Rival +{r['opp_rating'] - r['rating']}")
    if min(m["wb"] for m in r["moves"]) < 30 and r["outcome"] == "W":
        t.append("Remontada")
    if avg_loss(r) < median_loss * 0.5:
        t.append("Muy precisa")
    return t
