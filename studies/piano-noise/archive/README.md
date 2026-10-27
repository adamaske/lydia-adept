# Archive

- `report-2026-09-08/` — first, HbO-only report (subject 1).
- `sub-01-2026-09/` — HbO+HbR report for subject 1 (sessions 2026-09-07) with the NIRWizard
  exports it was built from. `report/report.tex` reads `../analysis/`, so keep the two together.
  Rebuild: `python analysis/report_figures.py`, then `latexmk -pdf -outdir=build report.tex` in `report/`.
