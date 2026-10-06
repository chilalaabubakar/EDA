"""Phase 4 (submission package) checks."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _contrast_on_white(hex_colour):
    def lin(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    h = hex_colour.lstrip("#")
    lum = 0.2126 * lin(h[0:2]) + 0.7152 * lin(h[2:4]) + 0.0722 * lin(h[4:6])
    return 1.05 / (lum + 0.05)


def test_figure_palette_is_the_house_one():
    """figures4papers palette: Rwanda dark blue, Kenya strong red, teal third."""
    import figures
    assert figures.SERIES == ["#0F4D92", "#B64342", "#42949E"]
    # every series line is readable on white (WCAG 3:1 for graphics)
    assert all(_contrast_on_white(c) >= 3 for c in figures.SERIES)
    # identity never by colour alone: each slot has its own marker and style
    assert len(set(figures.MARKERS)) == len(figures.SERIES)
    assert len(set(figures.STYLES)) == len(figures.SERIES)
    assert figures.DPI >= 300


def test_no_twin_axes_in_figures():
    src = (ROOT / "src" / "figures.py").read_text()
    assert "twinx" not in src and "twiny" not in src


def test_every_figure_has_a_caption():
    caps = (ROOT / "figures" / "captions.md").read_text()
    for n in range(1, 7):
        assert re.search(rf"\*\*Figure {n}\.", caps), f"Figure {n} caption missing"


def test_figures_render(tmp_path):
    import figures
    figures.fig1_structure(tmp_path)
    figures.fig2_cooking(tmp_path, seeds=range(2))
    assert (tmp_path / "fig1_model_structure.png").stat().st_size > 10_000
    assert (tmp_path / "fig2_cooking_profile.pdf").exists()


def test_abstract_template_fields_are_all_produced(tmp_path):
    """Every {field} in the abstract template must be a key the pipeline
    produces, so the abstract cannot carry a hand-typed number."""
    from manuscript_tables import headline_numbers, phase_numbers  # noqa: F401
    text = (ROOT / "manuscript" / "abstract_template.md").read_text()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    fields = {m.split(":")[0] for m in re.findall(r"\{([^}]+)\}", text)}
    src = (ROOT / "src" / "manuscript_tables.py").read_text()
    for f in fields:
        stem = re.sub(r"_(rwanda|kenya)(_lo|_hi)?$", "", f)
        assert stem.split("_")[0] in src or f in src, f"{f} not produced"


def test_raw_microdata_is_not_tracked():
    import subprocess
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True).stdout
    assert "SECTION_EF1.csv" not in out and "household_survey_data" not in out
    assert not re.search(r"manuscript/private/", out)
    assert ".docx" not in out


def test_submission_metadata_present():
    for f in ("CITATION.cff", ".zenodo.json", "LICENSE", "docs/DATA_ACCESS.md",
              "manuscript/nomenclature.md"):
        assert (ROOT / f).exists(), f


def test_resume_skips_finished_steps(tmp_path):
    """A rerun with --resume carries on after the last finished step."""
    import subprocess, sys
    cmd = [sys.executable, str(ROOT / "src" / "pipeline.py"), "validation",
           "--synthetic", "--quick", "--results", str(tmp_path)]
    first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    assert "done in" in first.stdout
    assert (tmp_path / ".steps_done").read_text().split() == ["validation"]
    again = subprocess.run(cmd + ["--resume"], cwd=ROOT, capture_output=True, text=True,
                           check=True)
    assert "already done, skipped" in again.stdout


def test_tables_are_rebuilt_after_every_analysis():
    """table7 and the ensemble numbers need phase 2-3 outputs, so `all` must
    build the tables once more after the last analysis step."""
    import pipeline
    order = list(pipeline.STEPS)
    assert "final_tables" in order
    for needed in ("ensemble", "operating_subsidy", "household_cost"):
        assert order.index(needed) < order.index("final_tables")
