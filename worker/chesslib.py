"""Utilidades de ajedrez: probabilidad de ganar, material, clasificación de errores."""
import math
import re
import chess

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAME = {chess.PAWN: "peón", chess.KNIGHT: "caballo", chess.BISHOP: "alfil", chess.ROOK: "torre", chess.QUEEN: "dama"}

KIND_LABEL = {
    "colgaste_movida": "Colgaste la pieza que acabás de mover",
    "colgaste_otra": "Dejaste otra pieza sin defensa",
    "horquilla": "Te comiste un ataque doble",
    "tactica_jaque": "Táctica con jaque",
    "tactica": "Otra táctica",
    "mate": "No viste un mate",
    "no_aprovechaste": "No castigaste un regalo del rival",
    "posicional": "Tiraste la ventaja sin perder material",
    "castigar": "El rival se equivocó: castigalo",
    "otro": "Otro",
}

# Errores que se evitan con el chequeo de jaques, capturas y amenazas
CHECK_KINDS = {"colgaste_movida", "colgaste_otra", "horquilla", "mate", "tactica_jaque", "tactica"}


def wp(cp):
    """Probabilidad de ganar (0-100) a partir de centipeones, fórmula de Lichess."""
    cp = max(-1500, min(1500, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def material(b, color):
    return sum(VAL[p.piece_type] for p in b.piece_map().values() if p.color == color)


def nonpawn(b):
    return sum(VAL[p.piece_type] for p in b.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))


def phase(b):
    if b.fullmove_number <= 10:
        return "apertura"
    q = bool(b.pieces(chess.QUEEN, chess.WHITE) or b.pieces(chess.QUEEN, chess.BLACK))
    return "final" if nonpawn(b) <= (14 if q else 26) else "medio juego"


def opening_family(eco_url):
    slug = eco_url.rsplit("/", 1)[-1] if eco_url else ""
    out = []
    for w in slug.split("-"):
        if re.match(r"^\d", w):
            break
        out.append(w)
        if w in ("Opening", "Defense", "Game", "Gambit", "Attack", "System"):
            break
    return " ".join(out[:5]) or "Apertura desconocida"


def san_line(fen, uci_list, n=4):
    """Convierte una lista UCI a notación con números de jugada."""
    b = chess.Board(fen)
    out = []
    for u in uci_list[:n]:
        m = chess.Move.from_uci(u)
        if m not in b.legal_moves:
            break
        s = b.san(m)
        if b.turn == chess.WHITE:
            s = f"{b.fullmove_number}.{s}"
        elif not out:
            s = f"{b.fullmove_number}…{s}"
        out.append(s)
        b.push(m)
    return " ".join(out)


def classify(b_before, move, reply_pv, me):
    """Tipo de error mirando la refutación del motor (PV desde la posición tras mi jugada)."""
    b = b_before.copy()
    mv = chess.Move.from_uci(move)
    mat0 = material(b, me) - material(b, not me)
    b.push(mv)
    if not reply_pv:
        return "otro", None
    r1 = chess.Move.from_uci(reply_pv[0])
    if r1 not in b.legal_moves:
        return "otro", None
    cap_piece = b.piece_at(r1.to_square)
    gives_check = b.gives_check(r1)
    hung = False
    if cap_piece and cap_piece.color == me:
        capturer = b.piece_at(r1.from_square)
        defended = b.is_attacked_by(me, r1.to_square)
        hung = (not defended) or VAL[capturer.piece_type] < VAL[cap_piece.piece_type]
    bb = b.copy()
    bb.push(r1)
    attacked = [s for s in bb.attacks(r1.to_square)
                if bb.piece_at(s) and bb.piece_at(s).color == me and
                (bb.piece_at(s).piece_type == chess.KING or VAL[bb.piece_at(s).piece_type] >= 3)]
    for u in reply_pv[1:6]:
        m = chess.Move.from_uci(u)
        if m not in bb.legal_moves:
            break
        bb.push(m)
    lost = mat0 - (material(bb, me) - material(bb, not me))
    if hung and r1.to_square == mv.to_square and lost >= 2:
        return "colgaste_movida", NAME.get(cap_piece.piece_type)
    if hung and lost >= 2:
        return "colgaste_otra", NAME.get(cap_piece.piece_type)
    if len(attacked) >= 2 and lost >= 2:
        return "horquilla", None
    if lost >= 2 and gives_check:
        return "tactica_jaque", None
    if lost >= 2:
        return "tactica", None
    return "posicional", None


def best_gain(b_before, pv, me):
    """Material que ganaba la línea del motor."""
    b = b_before.copy()
    mat0 = material(b, me) - material(b, not me)
    for u in pv[:6]:
        m = chess.Move.from_uci(u)
        if m not in b.legal_moves:
            break
        b.push(m)
    return (material(b, me) - material(b, not me)) - mat0
