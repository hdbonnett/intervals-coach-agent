# Diagram sources

| File | What it is |
|---|---|
| `reference-architecture.drawio` | Figure 1 as an editable draw.io / diagrams.net file |
| `build_reference.py` | Regenerates the `.drawio` file (needs `drawio_builder.py`; see its docstring) |
| `figures.py` | Generates `../images/fig1.svg` to `fig5.svg`, the figures in ARCHITECTURE.md (`python3 figures.py`, run from `../images`) |
| `drawio2svg.py` | Renders a layered `.drawio` file to a static SVG |
