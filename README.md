# aam-translator

Prepare geospatial inputs for the U.S. DOT **Advanced Acoustic Model** (AAM), and read
common outputs back.

The primary user of this library is [NPS ActiveSpace](https://github.com/dbetchkal/NPS-ActiveSpace), an open-source geospatial noise modeling project used by the United States National Park Service.

- `.ELV` — NMBGF elevation grid
- `.IMP` — NMBGF ground-impedance grid
- `.INP` — single-event AAM scenario input (Computation mode, calculation grid, terrain inputs, noise source tracks)
- `.POI`, `{basename}.txt`, `.Single.POI.csv` — see [Reading AAM output](docs/reading_aam_output.md)

```python
from aam_translator import write_terrain, load_terrain, write_inp, write_aam_inputs
from aam_translator import read_poi, read_run_log
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

- [DEM → AAM ELV pipeline](docs/elv_pipeline.md) — AEQD bilinear resample pipeline (implementation).
- [Reading AAM output](docs/reading_aam_output.md) — `.POI`, run logs, alignment checks, multi-point track guardrails.
- [References](references/README.md) — AAM `.inp` / NMBGF format specs and glossary (vendor manual/source local only).

