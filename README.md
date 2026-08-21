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

## Platform notes

- **Python 3.12** — required; other versions are not supported.
- **GDAL** — bundled with rasterio wheels on macOS, Linux, and Windows; no separate GDAL install is needed for typical use.
- **Clip sidecar GeoTIFF** — each `.ELV` gets a companion `*_clip.tif` for debugging. If that file is open in a GIS viewer, re-running the pipeline may fail until you close the viewer (Windows file locking is the most common case).

## Docs

- [DEM → AAM ELV pipeline](docs/elv_pipeline.md) — AEQD bilinear resample pipeline reference.
