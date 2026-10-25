# Coach fbiquard

Entrenador personal de ajedrez. Cada 2 horas un GitHub Action baja las partidas nuevas de rapid y blitz de chess.com, las analiza con Stockfish, convierte tus errores en ejercicios y le pide a Claude un consejo por partida. La web (GitHub Pages) muestra:

- **Repaso**: ejercicios de tus propias partidas con repetición espaciada (1, 3, 7, 21 y 60 días). El progreso se guarda en el navegador.
- **Partidas**: feed con momento clave, consejo, curva de chances y ejercicios de cada partida.
- **Diagnóstico**: patrones de error por ritmo, reloj, fases, aperturas y evolución.

## Estructura

```
worker/          pipeline en Python (corre en el Action)
  run.py         punto de entrada: baja, analiza y regenera la web
  engine.py      Stockfish
  game_report.py informe por partida y puzzles
  advice.py      consejo con Claude (o plantilla si no hay API key)
  stats.py       diagnóstico
data/evals/      evaluaciones jugada por jugada (historial)
data/reports/    informes completos por partida
site/            la web estática; site/data la genera el worker
```

## Puesta en marcha

1. **Secret**: Settings → Secrets and variables → Actions → New repository secret → `ANTHROPIC_API_KEY` (también se acepta `AJEDREZ`).
2. **Pages**: Settings → Pages → Source: **GitHub Actions**.
3. **Primera corrida**: Actions → "Actualizar partidas" → Run workflow.
4. **Dominio propio (opcional)**: Settings → Pages → Custom domain → `ajedrez.biquard.com`, y en el DNS de biquard.com un CNAME `ajedrez` → `fbiquard.github.io`.

## Correr local

```bash
pip install chess anthropic
export STOCKFISH=/ruta/a/stockfish
python worker/run.py
cd site && python -m http.server 8000
```

Variables útiles: `MAX_GAMES` (partidas por corrida), `THINK` (segundos de Stockfish por jugada), `MONTHS` (meses a revisar), `ADVICE_BACKFILL` (consejos viejos a reescribir con Claude por corrida), `CLAUDE_MODEL`.
