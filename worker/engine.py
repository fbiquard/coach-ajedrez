"""Análisis con Stockfish: evalúa cada jugada de una partida y busca soluciones alternativas para puzzles."""
import io
import os
import chess
import chess.engine
import chess.pgn

SF = os.environ.get("STOCKFISH", "stockfish")


def _score_cp(score):
    w = score.white()
    if w.is_mate():
        m = w.mate()
        return 10000 - abs(m) * 10 if m > 0 else -10000 + abs(m) * 10
    return w.score()


class Engine:
    def __init__(self, think_time=0.15):
        self.eng = chess.engine.SimpleEngine.popen_uci(SF)
        self.eng.configure({"Threads": int(os.environ.get("SF_THREADS", "2")), "Hash": 128})
        self.limit = chess.engine.Limit(time=think_time)

    def close(self):
        self.eng.quit()

    def _eval(self, b):
        if b.is_game_over():
            if b.is_checkmate():
                return (-10000 if b.turn == chess.WHITE else 10000), None, []
            return 0, None, []
        info = self.eng.analyse(b, self.limit)
        pv = info.get("pv", [])
        return _score_cp(info["score"]), (pv[0].uci() if pv else None), [m.uci() for m in pv[:6]]

    def analyse_game(self, pgn):
        """Devuelve la lista de jugadas con evaluación antes y después (cp desde blancas)."""
        game = chess.pgn.read_game(io.StringIO(pgn))
        board = game.board()
        plies = []
        e, best, pv = self._eval(board)
        node = game
        while node.variations:
            nxt = node.variations[0]
            mv = nxt.move
            fen = board.fen()
            san = board.san(mv)
            board.push(mv)
            e2, best2, pv2 = self._eval(board)
            plies.append(dict(fen=fen, move=mv.uci(), san=san, clk=nxt.clock(),
                              eval_before=e, best=best, pv=pv, eval_after=e2))
            e, best, pv = e2, best2, pv2
            node = nxt
        return plies

    def multipv(self, fen, n=2, think=0.25):
        """Las n mejores jugadas: lista de (uci, cp desde el bando que mueve, pv en uci)."""
        b = chess.Board(fen)
        me = b.turn
        out = []
        for inf in self.eng.analyse(b, chess.engine.Limit(time=think), multipv=n):
            if not inf.get("pv"):
                continue
            s = inf["score"].pov(me)
            cp = 10000 - 10 * s.mate() if s.is_mate() and s.mate() > 0 else (-10000 if s.is_mate() else s.score())
            out.append((inf["pv"][0].uci(), cp, [m.uci() for m in inf["pv"][:6]]))
        return out

    def solutions(self, fen, tolerance_cp=60, think=0.6):
        """Jugadas que valen como solución: la mejor y las que quedan muy cerca."""
        b = chess.Board(fen)
        infos = self.eng.analyse(b, chess.engine.Limit(time=think), multipv=3)
        me = b.turn
        scored = []
        for inf in infos:
            if not inf.get("pv"):
                continue
            s = inf["score"].pov(me)
            cp = 10000 - 10 * s.mate() if s.is_mate() and s.mate() > 0 else (-10000 if s.is_mate() else s.score())
            scored.append((inf["pv"][0].uci(), cp, [m.uci() for m in inf["pv"][:6]]))
        if not scored:
            return [], []
        top = scored[0][1]
        ok = [u for u, cp, _ in scored if cp >= top - tolerance_cp and (top < 9000 or cp >= 9000)]
        return ok, scored[0][2]
