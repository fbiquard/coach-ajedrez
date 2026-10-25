"""Plan de entrenamiento: reglas a partir de los patrones de error, con recursos reales y verificados.

Cada receta compara tus últimas 30 partidas del ritmo con las 30 anteriores, así se ve si mejora.
Los links del catálogo se verificaron a mano (oct 2026). No agregar recursos sin verificarlos.
"""
import statistics

WINDOW = 30

LI = "https://lichess.org"
R = {
    "drill": dict(name="Repaso diario de tus errores (esta app)", url="#repaso", dose="5 ejercicios por día"),
    "hanging": dict(name="Lichess · puzzles de pieza colgada", url=f"{LI}/training/hangingPiece", dose="10 por día"),
    "fork": dict(name="Lichess · puzzles de ataque doble", url=f"{LI}/training/fork", dose="10 por día"),
    "fork_practice": dict(name="Lichess Practice · The Fork", url=f"{LI}/practice/fundamental-tactics/practicestnamthefork/Qj281y1p", dose="una vez, completa"),
    "woodpecker": dict(name="Libro: The Woodpecker Method (Smith y Tikkanen)", url=None, dose="cuando los puzzles de Lichess te salgan fáciles"),
    "crushing": dict(name="Lichess · puzzles para castigar errores del rival", url=f"{LI}/training/crushing", dose="10 por día"),
    "advantage": dict(name="Lichess · puzzles de aprovechar la ventaja", url=f"{LI}/training/advantage", dose="5 por día"),
    "mate1": dict(name="Lichess · mate en 1", url=f"{LI}/training/mateIn1", dose="10 por día"),
    "mate2": dict(name="Lichess · mate en 2", url=f"{LI}/training/mateIn2", dose="5 por día"),
    "mate_patterns": dict(name="Lichess Practice · Checkmate Patterns I", url=f"{LI}/practice/checkmates/practicestnamcheckmatepatternsi/fE4k21MW", dose="una vez, completa"),
    "defensive": dict(name="Lichess · puzzles de jugada defensiva", url=f"{LI}/training/defensiveMove", dose="5 por día"),
    "advanced_pawn": dict(name="Lichess · puzzles de peón avanzado", url=f"{LI}/training/advancedPawn", dose="5 por día"),
    "deflection": dict(name="Lichess · puzzles de desviación", url=f"{LI}/training/deflection", dose="5 por día"),
    "rook_basic": dict(name="Lichess Practice · Basic Rook Endgames", url=f"{LI}/practice/rook-endgames/practicestnambasicrookendgames/pqUSUw8Y", dose="una vez, completa"),
    "key_squares": dict(name="Lichess Practice · Key Squares y Opposition", url=f"{LI}/practice/pawn-endgames/practicestnamkeysquares/xebrDvFe", dose="una vez, completas"),
    "rook_endgame": dict(name="Lichess · puzzles de finales de torre", url=f"{LI}/training/rookEndgame", dose="5 por día"),
    "silman": dict(name="Libro: Silman's Complete Endgame Course (Jeremy Silman)", url=None, dose="las secciones hasta tu nivel de rating, de a una por semana"),
    "middlegame": dict(name="Lichess · puzzles de medio juego", url=f"{LI}/training/middlegame", dose="10 por día"),
    "chernev": dict(name="Libro: Logical Chess: Move by Move (Irving Chernev)", url=None, dose="una partida comentada por día"),
    "explorer": dict(name="Lichess · explorador de aperturas", url=f"{LI}/analysis#explorer", dose="armá tu línea hasta la jugada 10"),
}

# Páginas de apertura de Lichess verificadas (las inexistentes redirigen)
OPENING_SLUG = {
    "Italian Game": "Italian_Game", "Giuoco Piano Game": "Italian_Game", "Sicilian Defense": "Sicilian_Defense",
    "Bishops Opening": "Bishops_Opening", "Caro Kann Defense": "Caro-Kann_Defense",
    "Scandinavian Defense": "Scandinavian_Defense", "French Defense": "French_Defense",
    "Queens Pawn Opening": "Queens_Pawn_Game", "Ruy Lopez Opening": "Ruy_Lopez", "Scotch Game": "Scotch_Game",
    "Kings Gambit": "Kings_Gambit", "Petrovs Defense": "Petrovs_Defense", "Four Knights Game": "Four_Knights_Game",
    "Vienna Game": "Vienna_Game", "Pirc Defense": "Pirc_Defense", "English Opening": "English_Opening",
    "Reti Opening": "Reti_Opening", "Queens Gambit": "Queens_Gambit", "Center Game": "Center_Game",
    "Philidor Defense": "Philidor_Defense", "Indian Game": "Indian_Defense",
}

HANG = {"colgaste_movida", "colgaste_otra", "horquilla"}
MISSED = {"castigar", "no_aprovechaste"}


def _per_game(games, fn):
    return round(sum(fn(r) for r in games) / len(games), 2) if games else None


def _blunders(r, kinds):
    return sum(1 for e in r["errors"] if e["sev"] == "blunder" and e["kind"] in kinds)


def _phase_rate(games, phase):
    n = sum(1 for r in games for m in r.get("moves", []) if m["phase"] == phase)
    b = sum(1 for r in games for e in r["errors"] if e["sev"] == "blunder" and e["phase"] == phase)
    return round(100 * b / n, 2) if n else None


def _conversion(games):
    won_pos = [r for r in games if r["max_wp"] >= 85]
    return (round(100 * sum(r["outcome"] == "W" for r in won_pos) / len(won_pos)) if won_pos else None), len(won_pos)


def _median_spent(games):
    xs = [m["spent"] for r in games for m in r.get("moves", []) if m["spent"] is not None and m["move_no"] > 8]
    return round(statistics.median(xs), 1) if xs else None


def _metric(label, now, before, target, better, unit=""):
    return dict(label=label, now=now, before=before, target=target, better=better, unit=unit)


def for_class(reports, tc):
    games = sorted([r for r in reports if r["time_class"] == tc], key=lambda r: -r["date"])
    now, before = games[:WINDOW], games[WINDOW:2 * WINDOW]
    if len(now) < 10:
        return None
    recs = []

    # 1. Piezas colgadas y ataques dobles
    hang_now = _per_game(now, lambda r: _blunders(r, HANG))
    total_b = sum(r["n_blunders"] for r in now)
    hang_n = sum(_blunders(r, HANG) for r in now)
    if hang_now and hang_now >= 0.15:
        recs.append(dict(
            id="colgar", area="Táctica", title="Dejar de colgar piezas",
            why=f"{hang_n} de tus {total_b} blunders en las últimas {len(now)} partidas fueron piezas colgadas o ataques dobles que no viste.",
            rule="Antes de soltar la pieza: ¿dónde queda?, ¿quién la ataca?, ¿qué jaques y capturas tiene el rival?",
            resources=[R["drill"], R["hanging"], R["fork"], R["fork_practice"], R["woodpecker"]],
            metric=_metric("piezas colgadas por partida", hang_now, _per_game(before, lambda r: _blunders(r, HANG)),
                           round(hang_now / 2, 2), "lower"),
            weight=hang_now * 10))

    # 2. Castigar los errores del rival
    miss_now = _per_game(now, lambda r: sum(1 for e in r["errors"] if e["kind"] in MISSED))
    if miss_now and miss_now >= 0.08:
        recs.append(dict(
            id="castigar", area="Táctica", title="Castigar los regalos del rival",
            why=f"En las últimas {len(now)} partidas el rival se equivocó y no lo aprovechaste {sum(1 for r in now for e in r['errors'] if e['kind'] in MISSED)} veces.",
            rule="Después de cada jugada del rival, antes de seguir tu plan: ¿qué me dejó? ¿qué atacó?",
            resources=[R["crushing"], R["advantage"]],
            metric=_metric("regalos no cobrados por partida", miss_now,
                           _per_game(before, lambda r: sum(1 for e in r["errors"] if e["kind"] in MISSED)),
                           round(miss_now / 2, 2), "lower"),
            weight=miss_now * 8))

    # 3. Mates que no viste
    mate_now = _per_game(now, lambda r: _blunders(r, {"mate"}))
    if mate_now and mate_now >= 0.04:
        recs.append(dict(
            id="mates", area="Táctica", title="Ver los mates (los tuyos y los del rival)",
            why=f"{sum(_blunders(r, {'mate'}) for r in now)} blunders en las últimas {len(now)} partidas permitieron mate.",
            rule="Antes de cada jugada, mirá los jaques del rival contra tu rey, todos.",
            resources=[R["mate_patterns"], R["mate1"], R["mate2"], R["defensive"]],
            metric=_metric("mates permitidos por partida", mate_now, _per_game(before, lambda r: _blunders(r, {"mate"})),
                           0.02, "lower"),
            weight=mate_now * 12))

    # 4. Convertir partidas ganadas
    conv_now, n_conv = _conversion(now)
    conv_before, _ = _conversion(before)
    if conv_now is not None and n_conv >= 8 and conv_now < 88:
        lost = n_conv - round(conv_now * n_conv / 100)
        recs.append(dict(
            id="convertir", area="Finales", title="Convertir las partidas ganadas",
            why=f"Llegaste a 85% de chances en {n_conv} partidas y {lost} no las ganaste.",
            rule="Con ventaja: cambiá piezas, no busques el golpe lindo. Antes de coronar, mirá quién controla la casilla.",
            resources=[R["advanced_pawn"], R["deflection"], R["rook_basic"], R["silman"]],
            metric=_metric("conversión de partidas ganadas", conv_now, conv_before, 92, "higher", "%"),
            weight=(88 - conv_now) / 10 + 1))

    # 5. Finales
    end_now = _phase_rate(now, "final")
    if end_now and end_now >= 1.5:
        recs.append(dict(
            id="finales", area="Finales", title="Técnica de finales",
            why=f"En los finales cometés {str(end_now).replace('.', ',')} blunders cada 100 jugadas.",
            rule="En el final el rey es una pieza más: activalo antes de mover los peones.",
            resources=[R["key_squares"], R["rook_basic"], R["rook_endgame"], R["silman"]],
            metric=_metric("blunders cada 100 jugadas de final", end_now, _phase_rate(before, "final"),
                           round(end_now * 0.6, 1), "lower"),
            weight=end_now / 2))

    # 6. Medio juego
    mid_now = _phase_rate(now, "medio juego")
    if mid_now and mid_now >= 2.0:
        recs.append(dict(
            id="medio", area="Medio juego", title="Medio juego con un plan",
            why=f"El medio juego es donde más te equivocás: {str(mid_now).replace('.', ',')} blunders cada 100 jugadas.",
            rule="Cada vez que no sabés qué jugar, buscá tu peor pieza y mejorala.",
            resources=[R["middlegame"], R["chernev"]],
            metric=_metric("blunders cada 100 jugadas de medio juego", mid_now, _phase_rate(before, "medio juego"),
                           round(mid_now * 0.7, 1), "lower"),
            weight=mid_now / 2.5))

    # 7. Una apertura puntual (todo el historial del ritmo, no solo la ventana)
    by = {}
    for r in games:
        k = (r["color"], r["opening"].split("...")[0])
        w, d, n = by.get(k, (0, 0, 0))
        by[k] = (w + (r["outcome"] == "W"), d + (r["outcome"] == "D"), n + 1)
    worst = sorted([(100 * (w + 0.5 * d) / n, n, c, o) for (c, o), (w, d, n) in by.items()
                    if n >= 10 and o not in ("Undefined", "Apertura desconocida")],
                   key=lambda x: x[0])
    if worst and worst[0][0] < 42:
        pct, n, color, name = worst[0]
        slug = OPENING_SLUG.get(name)
        nice = name.replace(" Game", "").replace(" Opening", "").replace(" Defense", "")
        res = ([dict(name=f"Lichess · {name}", url=f"{LI}/opening/{slug}", dose="leé la página y las líneas principales")]
               if slug else []) + [R["explorer"]]
        recs.append(dict(
            id="apertura", area="Apertura", title=f"Tu respuesta a la {nice} con {'blancas' if color == 'white' else 'negras'}",
            why=f"Con {'blancas' if color == 'white' else 'negras'}, en la {nice} sumás {round(pct)}% de los puntos en {n} partidas.",
            rule="Elegí una sola respuesta y jugala siempre, aunque no sea la más ambiciosa.",
            resources=res,
            metric=_metric(f"puntos en la {nice}", round(pct), None, 50, "higher", "%"),
            weight=(42 - pct) / 20))

    # 8. Uso del reloj (rapid)
    if tc == "rapid":
        sp = _median_spent(now)
        if sp is not None and sp < 15:
            recs.append(dict(
                id="reloj", area="Reloj", title="Usar el reloj",
                why=f"Pensás {str(sp).replace('.', ',')} segundos por jugada (mediana, desde la jugada 9): rapid jugado a ritmo de blitz.",
                rule="Desde la jugada 10, mínimo 20 segundos por jugada, usados en el chequeo de jaques, capturas y amenazas.",
                resources=[dict(name="Jugá 15+10 o más largo", url=None, dose="durante estas 4 semanas")],
                metric=_metric("segundos por jugada (mediana)", sp, _median_spent(before), 20, "higher", "s"),
                weight=(15 - sp) / 3 + 1))

    recs.sort(key=lambda x: -x["weight"])
    for x in recs:
        x.pop("weight")
    return dict(time_class=tc, window=len(now), before=len(before), focus=recs[:3], later=recs[3:])


def build(reports):
    return {tc: p for tc in ("rapid", "blitz") if (p := for_class(reports, tc))}
