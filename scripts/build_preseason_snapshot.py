"""Run the hardcoded preseason Monte Carlo and write JSON, HTML, and CSV."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nba2027.data_load import load_inputs  # noqa: E402
from nba2027.parameters import N_INNER, N_OUTER, RANDOM_SEED  # noqa: E402
from nba2027.simulate import run_monte_carlo  # noqa: E402
from nba2027.snapshot import build_document, render_html, write_csv  # noqa: E402


def main() -> None:
    inputs = load_inputs(ROOT / "data")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    if inputs["missing_priors"]:
        document = build_document(None, inputs)
    else:
        def progress(done: int, total: int) -> None:
            print(f"外层样本 {done}/{total}", flush=True)

        result = run_monte_carlo(inputs, n_outer=N_OUTER, n_inner=N_INNER, seed=RANDOM_SEED, progress=progress)
        document = build_document(result, inputs)
    json_path = output / "preseason-2026-27.json"
    html_path = output / "preseason-2026-27.html"
    csv_path = output / "preseason-2026-27.csv"
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(document), encoding="utf-8")
    write_csv(document, csv_path)
    print(json_path)
    print(html_path)
    if document["probabilities_published"]:
        print(
            f"N={document['n_simulations']} seed={document['random_seed']} "
            f"rounded_sum={document['rounded_percent_sum']}"
        )


if __name__ == "__main__":
    main()
