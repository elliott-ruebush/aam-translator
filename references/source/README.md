# AAM reference Fortran

Small extracts from the AAM / NMBGF toolchain for cross-checking NMBGF header semantics.

| File | Role |
|------|------|
| [`Plt2Elv.f`](Plt2Elv.f) | Volpe utility: ASCII `.PLT` grid → binary `.ELV` / `.IMP` / `.FOL` (NMBGF). Shows authoritative `FEET`, `DIDJ`, `XRYR`, and `ZALT` write order. |

**Why it matters:** `Plt2Elv` is the ground truth for how vendor NMBGF terrain files declare grid geometry. See [`notes/aam_nmbgf.md`](../notes/aam_nmbgf.md) for header fields, extent, and this package's grid-local FEET convention.

**Provenance:** excerpt from AAM source (Juliet Page, Wyle/Volpe; updates through 2020).
