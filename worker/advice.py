"""Consejo por partida: lo escribe Claude a partir de los datos del motor; si no hay API key, usa plantillas."""
import json
import os

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM = """Sos el entrenador de ajedrez personal de Fede (usuario fbiquard en chess.com, ~1300 en rapid, ~950 en blitz).
Escribís en castellano rioplatense, directo, sin vueltas y sin elogios vacíos.
Te paso los datos de una partida ya analizada con Stockfish. Reglas:
- No calcules variantes ni inventes jugadas: usá solo las jugadas y líneas que aparecen en los datos.
- Contá qué decidió la partida (el momento clave) y dejá UN hábito concreto para la próxima.
- Si ganó gracias a errores del rival, decilo.
- Máximo 3 oraciones cortas, en un solo párrafo, sin listas ni títulos. Usá notación en inglés (N, B, R, Q, K) como en los datos.
Números: porcentajes redondeados a enteros, coma decimal, y nada de métricas técnicas como "pérdida media": decilo en palabras ("casi sin imprecisiones", "el doble de preciso que de costumbre")."""

RES = {"W": "ganó", "D": "empató", "L": "perdió"}


def facts(r):
    keep = ["move_no", "phase", "label", "played", "best", "best_line", "refutation", "wb", "wa", "clk"]
    return dict(
        ritmo=r["time_class"], color=("blancas" if r["color"] == "white" else "negras"),
        resultado=RES[r["outcome"]], apertura=r["opening"], rating=r["rating"], rating_rival=r["opp_rating"],
        max_chances_de_ganar=r["max_wp"], se_le_escapo_una_ganada=r["blown"],
        errores_propios=[{k: e[k] for k in keep} for e in sorted(r["errors"], key=lambda e: -e["loss"])[:4]],
        errores_del_rival=r["opp_errors"][:4], jugadas=r["n_moves"])


def template(r):
    errs = sorted(r["errors"], key=lambda e: -e["loss"])
    if not errs:
        if r["outcome"] == "W":
            return "Partida limpia: ningún error grave tuyo. Así se gana: sin regalar nada."
        return "No cometiste errores graves; la partida se definió por detalles. Revisá la apertura y los planes del medio juego."
    e = errs[0]
    head = f"El momento clave fue la jugada {e['move_no']}: {e['text']}"
    if r["blown"]:
        tail = f" Llegaste a {r['max_wp']}% de chances y la soltaste: cuando estés ganado, hacé el chequeo de jaques, capturas y amenazas dos veces."
    elif r["outcome"] == "W" and r["opp_errors"] and e["sev"] == "blunder":
        tail = " Ganaste, pero porque el rival se equivocó último. El chequeo antes de soltar la pieza es lo que te falta."
    else:
        tail = " Antes de soltar la pieza: ¿qué jaques, capturas y amenazas tiene el rival?"
    return head + tail


def write(r):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return dict(text=template(r), source="plantilla")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts(r), ensure_ascii=False)}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if text and msg.stop_reason == "end_turn":
            return dict(text=text, source="claude", v=3)
        print("Claude: respuesta incompleta, uso plantilla:", msg.stop_reason)
    except Exception as exc:  # si falla la API, no frenamos el pipeline
        print("advice: falló Claude:", exc)
    return dict(text=template(r), source="plantilla")
