# aam-translator

Prepare geospatial inputs for the U.S. DOT **Advanced Acoustic Model** (AAM):

- `.ELV` — NMBGF elevation grid
- `.IMP` — NMBGF ground-impedance grid
- `.INP` — single-event AAM scenario input (Computation mode, calculation grid, terrain inputs, noise source tracks)

```python
from aam_translator import write_terrain, write_inp, write_aam_inputs
```

Requires Python 3.12 only (`requires-python = ">=3.12,<3.13"`). Install in another project with:

```
pip install -e /path/to/aam_translator
```

## Docs

- [DEM → AAM ELV pipeline](docs/elv_pipeline.md) — AEQD bilinear resample pipeline reference.
