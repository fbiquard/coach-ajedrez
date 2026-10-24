"""Carga inicial: toma partidas ya evaluadas (formato {meta, plies}) y genera sus informes."""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run  # noqa: E402
from engine import Engine  # noqa: E402

SRC_EVALS = sys.argv[1:-1]
RAW = sys.argv[-1]  # carpeta con los archivos mensuales crudos de chess.com, para el nombre del rival

names = {}
for f in glob.glob(f"{RAW}/*.json"):
    for g in json.load(open(f)).get("games", []):
        me = "white" if g["white"]["username"].lower() == run.USER.lower() else "black"
        names[g["uuid"]] = g["black" if me == "white" else "white"]["username"]

for d in (run.EVALS, run.REPORTS, run.SITE):
    d.mkdir(parents=True, exist_ok=True)
eng = Engine(float(os.environ.get("THINK", "0.15")))
seen = set()
for src in SRC_EVALS:
    for f in sorted(glob.glob(f"{src}/*.json")):
        d = json.load(open(f))
        meta = d["meta"]
        if meta["uuid"] in seen:
            continue
        seen.add(meta["uuid"])
        meta["opp_name"] = names.get(meta["uuid"], "")
        (run.EVALS / f"{meta['uuid']}.json").write_text(json.dumps(dict(meta=meta, plies=d["plies"]), separators=(",", ":")))
        run.finish(meta, d["plies"], eng)
        if len(seen) % 50 == 0:
            print(len(seen), flush=True)
eng.close()
print("seed:", len(seen), "partidas;", run.rebuild_site())
