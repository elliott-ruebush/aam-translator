# aam-translator

Prepare geospatial inputs for the U.S. DOT **Advanced Acoustic Model** (AAM):

- `.ELV` — NMBGF elevation grid
- `.IMP` — NMBGF ground-impedance grid
- `.INP` — single-event AAM scenario input (Computation mode, calculation grid, terrain inputs, noise source tracks)

```python
from aam_translator import write_terrain, write_inp, write_aam_inputs
```

Requires Python >=3.12 (tested on 3.12). Install in another project with:

```
pip install git+https://github.com/elliott-ruebush/aam-translator.git
```

Or from a local clone:

```
pip install -e /path/to/aam_translator
```

## Platform notes

- **Python >=3.12** — required; CI tests on 3.12 only.
- **GDAL** — bundled with rasterio wheels on macOS, Linux, and Windows; no separate GDAL install is needed for typical use.

## Docs

- [DEM → AAM ELV pipeline](docs/elv_pipeline.md) — AEQD bilinear resample pipeline reference.
