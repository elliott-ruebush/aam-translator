"""Regenerate PNG figures for docs/elv_pipeline.md.

Not a package API. Requires matplotlib in the environment
(``uv pip install matplotlib``; it is not a runtime dependency).

Synthetic Triple Lakes–like geometry only — does not read a DEM.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from pyproj import CRS, Transformer

# Okabe–Ito
BLUE = "#0072B2"
SKY = "#56B4E9"
ORANGE = "#E69F00"
GREEN = "#009E73"
VERMILLION = "#D55E00"
GRAY = "#4D4D4D"
LIGHT_GRAY = "#B0B0B0"

DPI = 180
OUT_DIR = Path(__file__).resolve().parent / "figures"

# Triple Lakes trailhead-ish (Denali entrance), UTM zone 6N
LON0, LAT0 = -148.90, 63.73
UTM_EPSG = 32606
TILE_W_M = 9000.0
TILE_H_M = 4000.0
DX_M = 30.0
DY_M = 30.0


def _transformers() -> tuple[Transformer, Transformer, CRS]:
    utm = CRS.from_epsg(UTM_EPSG)
    aeqd = CRS.from_proj4(
        f"+proj=aeqd +lat_0={LAT0} +lon_0={LON0} +datum=WGS84 +units=m +no_defs",
    )
    to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    utm_to_aeqd = Transformer.from_crs(utm, aeqd, always_xy=True)
    return to_utm, utm_to_aeqd, aeqd


def utm_tile_corners() -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    """Return UTM and AEQD corner arrays (SW, SE, NE, NW) and UTM SW."""
    to_utm, utm_to_aeqd, _ = _transformers()
    cx, cy = to_utm.transform(LON0, LAT0)
    minx, miny = cx - TILE_W_M / 2.0, cy - TILE_H_M / 2.0
    maxx, maxy = cx + TILE_W_M / 2.0, cy + TILE_H_M / 2.0
    utm_xy = np.array(
        [
            [minx, miny],
            [maxx, miny],
            [maxx, maxy],
            [minx, maxy],
        ]
    )
    aeqd_x, aeqd_y = utm_to_aeqd.transform(utm_xy[:, 0], utm_xy[:, 1])
    aeqd_xy = np.column_stack([aeqd_x, aeqd_y])
    return utm_xy, aeqd_xy, (minx, miny)


def _closed(xy: np.ndarray) -> np.ndarray:
    return np.vstack([xy, xy[0]])


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def fig_utm_vs_aeqd(path: Path) -> float:
    """Figure 1: UTM parallelogram vs fake AEQD rectangle vs true AABB."""
    _utm_xy, aeqd_xy, _ = utm_tile_corners()
    sw = aeqd_xy[0]
    fake = np.array(
        [
            sw,
            sw + [TILE_W_M, 0.0],
            sw + [TILE_W_M, TILE_H_M],
            sw + [0.0, TILE_H_M],
        ]
    )
    true_ne = aeqd_xy[2]
    fake_ne = fake[2]
    offset_m = float(np.hypot(*(true_ne - fake_ne)))

    aabb_min = aeqd_xy.min(axis=0)
    aabb_max = aeqd_xy.max(axis=0)
    aabb = np.array(
        [
            [aabb_min[0], aabb_min[1]],
            [aabb_max[0], aabb_min[1]],
            [aabb_max[0], aabb_max[1]],
            [aabb_min[0], aabb_max[1]],
        ]
    )

    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    utm_poly = _closed(aeqd_xy)
    ax.fill(utm_poly[:, 0], utm_poly[:, 1], color=SKY, alpha=0.22, zorder=1)
    ax.plot(
        utm_poly[:, 0],
        utm_poly[:, 1],
        color=BLUE,
        lw=2.0,
        zorder=3,
        label="UTM tile in AEQD",
    )
    ax.plot(
        *_closed(fake).T,
        color=VERMILLION,
        lw=1.8,
        ls="--",
        zorder=4,
        label=r"Fake AEQD rect  $SW+(n_x\,\Delta x,\,n_y\,\Delta y)$",
    )
    ax.plot(
        *_closed(aabb).T,
        color=GREEN,
        lw=1.8,
        ls="-.",
        zorder=2,
        label="True axis-aligned AEQD bbox",
    )
    ax.plot(0.0, 0.0, marker="+", ms=10, mew=1.6, color="black", zorder=5)
    ax.annotate(
        "AEQD origin\n(AOI centroid)",
        xy=(0.0, 0.0),
        xytext=(250, 280),
        fontsize=8,
        color=GRAY,
        ha="left",
        va="bottom",
        arrowprops=dict(arrowstyle="-", color=GRAY, lw=0.8),
    )

    ax.annotate(
        "",
        xy=true_ne,
        xytext=fake_ne,
        arrowprops=dict(arrowstyle="<->", color=VERMILLION, lw=1.4),
        zorder=6,
    )
    mid = 0.5 * (true_ne + fake_ne)
    ax.annotate(
        f"NE offset\n{offset_m:.0f} m",
        xy=mid,
        xytext=(mid[0] - 2100, mid[1] + 150),
        fontsize=9,
        color=VERMILLION,
        fontweight="bold",
        ha="center",
        arrowprops=dict(arrowstyle="-", color=VERMILLION, lw=0.7),
    )

    axins = ax.inset_axes([0.58, 0.06, 0.40, 0.38])
    axins.fill(utm_poly[:, 0], utm_poly[:, 1], color=SKY, alpha=0.22)
    axins.plot(*utm_poly.T, color=BLUE, lw=1.8)
    axins.plot(*_closed(fake).T, color=VERMILLION, lw=1.5, ls="--")
    axins.plot(*_closed(aabb).T, color=GREEN, lw=1.5, ls="-.")
    axins.annotate(
        "",
        xy=true_ne,
        xytext=fake_ne,
        arrowprops=dict(arrowstyle="<->", color=VERMILLION, lw=1.3),
    )
    pad = 180.0
    xs = [true_ne[0], fake_ne[0]]
    ys = [true_ne[1], fake_ne[1]]
    axins.set_xlim(min(xs) - pad, max(xs) + pad)
    axins.set_ylim(min(ys) - pad, max(ys) + pad)
    axins.set_aspect("equal")
    axins.set_title("NE zoom", fontsize=8, pad=2)
    axins.tick_params(labelsize=7)
    ax.indicate_inset_zoom(axins, edgecolor="0.45", lw=0.8)

    ax.set_aspect("equal")
    ax.set_xlabel("AEQD easting (m)")
    ax.set_ylabel("AEQD northing (m)")
    ax.set_title(
        "Legacy UTM-index copy vs true AEQD bbox (current writer resamples at centers)",
        loc="left",
        pad=8,
    )
    ax.legend(loc="upper left", frameon=True, fancybox=False, edgecolor="#DDDDDD")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return offset_m


def fig_cell_center_vs_corner(path: Path) -> None:
    """Figure 2: cartoon 4×3 grid — origin at SW corner, Z at centers."""
    nx, ny = 4, 3
    dx, dy = DX_M, DY_M

    fig, ax = plt.subplots(figsize=(6.6, 5.0))
    for i in range(nx):
        for j in range(ny):
            is_first = i == 0 and j == 0
            rect = Rectangle(
                (i * dx, j * dy),
                dx,
                dy,
                facecolor=SKY if is_first else "white",
                edgecolor=GRAY,
                lw=1.4,
                zorder=2,
            )
            ax.add_patch(rect)
            cx, cy = (i + 0.5) * dx, (j + 0.5) * dy
            ax.plot(cx, cy, "o", color=ORANGE, ms=8, zorder=4, markeredgecolor="white")
            ax.text(
                cx,
                cy + 4.6,
                f"({i},{j})",
                ha="center",
                va="bottom",
                fontsize=8,
                color=GRAY,
                zorder=5,
            )

    ax.plot(
        0.0,
        0.0,
        marker="s",
        ms=9,
        color="black",
        zorder=6,
        markeredgecolor="white",
        markeredgewidth=0.6,
    )
    ax.annotate(
        r"XRYR = (0, 0)" + "\nSW corner of cell (0, 0)",
        xy=(0.0, 0.0),
        xytext=(-38, -22),
        fontsize=8.5,
        ha="left",
        va="top",
        arrowprops=dict(arrowstyle="->", color="black", lw=1.0),
    )
    ax.annotate(
        "First NMBGF cell\n(SW, j-reversed)",
        xy=(0.45 * dx, 0.22 * dy),
        xytext=(1.15 * dx, -0.85 * dy),
        fontsize=8.5,
        color=BLUE,
        ha="left",
        arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0),
    )

    # DIDJ along the south edge of cell (1,0)
    y_dim = -0.18 * dy
    ax.annotate(
        "",
        xy=(2 * dx, y_dim),
        xytext=(1 * dx, y_dim),
        arrowprops=dict(arrowstyle="<->", color=GREEN, lw=1.2),
        annotation_clip=False,
    )
    ax.text(
        1.5 * dx,
        y_dim - 4.5,
        r"DIDJ  $\Delta x$ (metric posting)",
        ha="center",
        va="top",
        fontsize=8,
        color=GREEN,
        clip_on=False,
    )

    legend_handles = [
        Rectangle((0, 0), 1, 1, facecolor=SKY, edgecolor=GRAY, lw=1.2, label="First payload cell"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=ORANGE,
            markeredgecolor="white",
            ms=8,
            label="Cell center (ZALT sample)",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            color="none",
            markerfacecolor="black",
            ms=8,
            label="Model origin (corner)",
        ),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper right",
        frameon=True,
        fancybox=False,
        edgecolor="#DDDDDD",
    )
    ax.set_xlim(-1.55 * dx, nx * dx + 0.45 * dx)
    ax.set_ylim(-1.35 * dy, ny * dy + 0.55 * dy)
    ax.set_aspect("equal")
    ax.set_xlabel("model i  →  east  (m on the AEQD plane)")
    ax.set_ylabel("model j  →  north  (m on the AEQD plane)")
    ax.set_title("Origin is a corner; ZALT is a center sample", loc="left", pad=8)
    ax.set_xticks([i * dx for i in range(nx + 1)])
    ax.set_yticks([j * dy for j in range(ny + 1)])
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def fig_aeqd_sample_centers(path: Path) -> None:
    """Figure 3: AEQD cell-center lattice vs parent UTM pixel centers."""
    _utm_xy, aeqd_xy, (utm_minx, utm_miny) = utm_tile_corners()
    _, utm_to_aeqd, _ = _transformers()

    aabb_min = aeqd_xy.min(axis=0)
    nx_aeqd = int(np.ceil((aeqd_xy[:, 0].max() - aabb_min[0]) / DX_M))
    ny_aeqd = int(np.ceil((aeqd_xy[:, 1].max() - aabb_min[1]) / DY_M))
    aeqd_cx = aabb_min[0] + (np.arange(nx_aeqd) + 0.5) * DX_M
    aeqd_cy = aabb_min[1] + (np.arange(ny_aeqd) + 0.5) * DY_M

    # Zoom near the NE, where the UTM/AEQD mismatch is obvious.
    true_ne = aeqd_xy[2]
    xlim = (true_ne[0] - 165.0, true_ne[0] + 45.0)
    ylim = (true_ne[1] - 125.0, true_ne[1] + 40.0)

    nx_utm = int(round(TILE_W_M / DX_M))
    ny_utm = int(round(TILE_H_M / DY_M))
    pad_cells = 3
    # Inverse-ish crop: keep UTM cells whose AEQD centers fall near the zoom.
    utm_cx = utm_minx + (np.arange(nx_utm) + 0.5) * DX_M
    utm_cy = utm_miny + (np.arange(ny_utm) + 0.5) * DY_M
    ucx, ucy = np.meshgrid(utm_cx, utm_cy)
    ucx_a, ucy_a = utm_to_aeqd.transform(ucx, ucy)
    near = (
        (ucx_a >= xlim[0] - DX_M * pad_cells)
        & (ucx_a <= xlim[1] + DX_M * pad_cells)
        & (ucy_a >= ylim[0] - DY_M * pad_cells)
        & (ucy_a <= ylim[1] + DY_M * pad_cells)
    )
    rows = np.where(near.any(axis=1))[0]
    cols = np.where(near.any(axis=0))[0]
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    c0, c1 = int(cols.min()), int(cols.max()) + 1

    utm_x_g = utm_minx + np.arange(c0, c1 + 1) * DX_M
    utm_y_g = utm_miny + np.arange(r0, r1 + 1) * DY_M
    xx, yy = np.meshgrid(utm_x_g, utm_y_g)
    ax_g, ay_g = utm_to_aeqd.transform(xx, yy)

    # Synthetic planar ramp in UTM — scale to the visible window so the
    # gradient reads (full-tile 0–360 m would look flat here).
    z = (xx[:-1, :-1] - xx[:-1, :-1].min()) * 0.12 + (
        yy[:-1, :-1] - yy[:-1, :-1].min()
    ) * 0.06

    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    mesh = ax.pcolormesh(
        ax_g,
        ay_g,
        z,
        cmap="cividis",
        shading="flat",
        alpha=0.9,
        zorder=1,
        linewidth=0,
        rasterized=True,
    )
    for row in range(ax_g.shape[0]):
        ax.plot(ax_g[row, :], ay_g[row, :], color=LIGHT_GRAY, lw=0.55, zorder=2)
    for col in range(ax_g.shape[1]):
        ax.plot(ax_g[:, col], ay_g[:, col], color=LIGHT_GRAY, lw=0.55, zorder=2)

    utm_in = (
        (ucx_a >= xlim[0] - DX_M)
        & (ucx_a <= xlim[1] + DX_M)
        & (ucy_a >= ylim[0] - DY_M)
        & (ucy_a <= ylim[1] + DY_M)
    )
    ax.plot(
        ucx_a[utm_in],
        ucy_a[utm_in],
        "x",
        color=VERMILLION,
        ms=7,
        mew=1.4,
        zorder=4,
        label="UTM pixel centers",
    )

    acx, acy = np.meshgrid(aeqd_cx, aeqd_cy)
    aeqd_in = (
        (acx >= xlim[0] - DX_M)
        & (acx <= xlim[1] + DX_M)
        & (acy >= ylim[0] - DY_M)
        & (acy <= ylim[1] + DY_M)
    )
    ax.plot(
        acx[aeqd_in],
        acy[aeqd_in],
        "o",
        color=SKY,
        ms=7,
        markeredgecolor=BLUE,
        markeredgewidth=0.9,
        zorder=5,
        label="AEQD cell centers (sample here)",
    )

    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("synthetic elevation (m), exaggerated ramp")

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.set_xlabel("AEQD easting (m)")
    ax.set_ylabel("AEQD northing (m)")
    ax.set_title("Bilinear-sample parent DEM at AEQD centers", loc="left", pad=8)
    ax.legend(loc="upper left", frameon=True, fancybox=False, edgecolor="#DDDDDD")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _style()
    p1 = OUT_DIR / "utm_vs_aeqd.png"
    p2 = OUT_DIR / "cell_center_vs_corner.png"
    p3 = OUT_DIR / "aeqd_sample_centers.png"
    offset = fig_utm_vs_aeqd(p1)
    fig_cell_center_vs_corner(p2)
    fig_aeqd_sample_centers(p3)
    print(f"NE offset: {offset:.1f} m")
    for p in (p1, p2, p3):
        print(f"wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
