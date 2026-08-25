# Vendor AAM source — local only

Fortran extracts from the AAM / NMBGF toolchain are **gitignored** — copy from your AAM install or NPS data drive. Not redistributed in this public repo.

| File | Role |
|------|------|
| `Plt2Elv.f` | Volpe utility: ASCII `.PLT` grid → binary `.ELV` / `.IMP` / `.FOL` (NMBGF). Shows authoritative `FEET`, `DIDJ`, `XRYR`, and `ZALT` write order. |

**Why it matters:** `Plt2Elv` is the ground truth for how vendor NMBGF terrain files declare grid geometry. See [`notes/aam_nmbgf.md`](../notes/aam_nmbgf.md) for header fields, extent, and this package's grid-local FEET convention.

**Provenance:** excerpt from AAM source (Juliet Page, Wyle/Volpe; updates through 2020).
