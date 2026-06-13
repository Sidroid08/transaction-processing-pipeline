"""Render docs/architecture.drawio to a PNG that mirrors the same diagram.

Box coordinates, sizes, colours, shapes, text, alignment, the boundary note and
all 10 numbered edges (including the dashed Client -> API -> DB read path) are
taken directly from architecture.drawio so the PNG is a faithful 1:1 export.
Run: python docs/render_architecture.py
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

MAXY = 560  # drawio y grows downward; flip into matplotlib's upward y-axis.

# fill, stroke
BLUE = ("#dae8fc", "#6c8ebf")
GREEN = ("#d5e8d4", "#82b366")
RED = ("#f8cecc", "#b85450")
ORANGE = ("#ffe6cc", "#d79b00")
PURPLE = ("#e1d5e7", "#9673a6")
YELLOW = ("#fff2cc", "#d6b656")
LLMBLUE = ("#d4e1f5", "#6c8ebf")
GREY = ("#f5f5f5", "#666666")

# id -> dict(x, y, w, h, text, colors, align, shape, dashed, fs)  -- matches drawio
BOXES = {
    "client": dict(
        x=60, y=120, w=140, h=70,
        text="Client\n(curl / Swagger UI)",
        colors=BLUE, align="center", shape="round", dashed=False, fs=9.2,
    ),
    "api": dict(
        x=280, y=100, w=230, h=125,
        text="FastAPI (api)\nPOST /jobs/upload\nGET /jobs/{id}/status\nGET /jobs/{id}/results\nGET /jobs?status={status}",
        colors=GREEN, align="left", shape="round", dashed=False, fs=9.2,
    ),
    "redis": dict(
        x=620, y=60, w=190, h=80,
        text="Redis\n(Celery broker +\nresult backend)",
        colors=RED, align="center", shape="round", dashed=False, fs=9.2,
    ),
    "worker": dict(
        x=620, y=190, w=240, h=180,
        text="Celery Worker\nPipeline:\na) clean + dedupe\nb) anomaly detection\nc) LLM classify (batched)\nd) narrative summary\ne) retry with backoff\nf) mark failed if needed",
        colors=ORANGE, align="left", shape="round", dashed=False, fs=9.2,
    ),
    "db": dict(
        x=320, y=330, w=170, h=100,
        text="PostgreSQL\njobs / transactions\n/ job_summaries",
        colors=PURPLE, align="center", shape="cylinder", dashed=False, fs=9.2,
    ),
    "volume": dict(
        x=320, y=480, w=220, h=70,
        text="Shared Volume\n/data/uploads/{job_id}.csv\n(local Docker storage)",
        colors=YELLOW, align="center", shape="round", dashed=True, fs=9.2,
    ),
    "llm": dict(
        x=920, y=230, w=190, h=95,
        text="LLM Provider\nGemini 1.5 Flash\n(fallback: local\ndeterministic stub)",
        colors=LLMBLUE, align="center", shape="round", dashed=False, fs=9.2,
    ),
    "note": dict(
        x=60, y=300, w=220, h=70,
        text="Important boundary: clients never\nread PostgreSQL directly. All reads/\nwrites go through the FastAPI service.",
        colors=GREY, align="left", shape="round", dashed=True, fs=8,
    ),
}

# src, dst, label, dashed, double, waypoints(drawio coords), label_pos(drawio coords)
EDGES = [
    ("client", "api", "1. upload CSV", False, False, None, None),
    ("api", "volume", "2. save raw CSV", False, False, None, None),
    ("api", "db", "3. create job record (pending)", False, False, None, None),
    ("api", "redis", "4. enqueue task", False, False, None, None),
    ("redis", "worker", "5. dequeue task", False, False, None, None),
    ("worker", "volume", "6. read CSV", True, False, None, None),
    ("worker", "llm", "7. classify + summarize", False, False, None, None),
    ("worker", "db", "8. persist results + summary;\nmark completed/failed", False, False, None, None),
    ("client", "api", "9. poll status / results", True, False,
     [(130, 255), (395, 255)], (262, 250)),
    ("api", "db", "10. read status / results", True, False,
     [(535, 270), (535, 380)], (560, 300)),
]


def mpl_rect(b):
    return b["x"], MAXY - b["y"] - b["h"], b["w"], b["h"]


def center(key):
    b = BOXES[key]
    return b["x"] + b["w"] / 2, MAXY - b["y"] - b["h"] / 2


def to_mpl(p):
    return p[0], MAXY - p[1]


def add_cylinder(ax, b):
    x, y, w, h = mpl_rect(b)
    fill, stroke = b["colors"]
    eh = 20
    ax.add_patch(Rectangle((x, y + eh / 2), w, h - eh, facecolor=fill, edgecolor="none", zorder=1))
    ax.plot([x, x], [y + eh / 2, y + h - eh / 2], color=stroke, lw=1.6, zorder=2)
    ax.plot([x + w, x + w], [y + eh / 2, y + h - eh / 2], color=stroke, lw=1.6, zorder=2)
    ax.add_patch(
        Ellipse((x + w / 2, y + eh / 2), w, eh, facecolor=fill, edgecolor=stroke, lw=1.6, zorder=2)
    )
    ax.add_patch(Rectangle((x, y + eh / 2), w, eh / 2, facecolor=fill, edgecolor="none", zorder=3))
    ax.add_patch(
        Ellipse(
            (x + w / 2, y + h - eh / 2), w, eh, facecolor=fill, edgecolor=stroke, lw=1.6, zorder=4
        )
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(15, 7.6), dpi=160)
    ax.set_xlim(30, 1130)
    ax.set_ylim(0, 580)
    ax.axis("off")

    ax.text(
        570, 555, "AI-Powered Transaction Processing Pipeline — Architecture",
        ha="center", va="center", fontsize=17, fontweight="bold",
    )

    patches = {}
    for key, b in BOXES.items():
        x, y, w, h = mpl_rect(b)
        fill, stroke = b["colors"]
        if b["shape"] == "cylinder":
            add_cylinder(ax, b)
            patch = Rectangle((x, y), w, h, facecolor="none", edgecolor="none")
            ax.add_patch(patch)
        else:
            patch = FancyBboxPatch(
                (x, y), w, h,
                boxstyle="round,pad=2,rounding_size=8",
                linewidth=1.6, edgecolor=stroke, facecolor=fill,
                linestyle="--" if b["dashed"] else "-", mutation_aspect=1, zorder=1,
            )
            ax.add_patch(patch)
        patches[key] = patch

        cx, cy = center(key)
        if b["align"] == "left":
            ty = cy if b["shape"] != "cylinder" else cy - 6
            ax.text(x + 12, ty, b["text"], ha="left", va="center", fontsize=b["fs"],
                    color="#222222", zorder=5)
        else:
            ty = cy if b["shape"] != "cylinder" else cy - 6
            ax.text(cx, ty, b["text"], ha="center", va="center", fontsize=b["fs"],
                    color="#222222", zorder=5)

    for src, dst, label, dashed, double, wps, lpos in EDGES:
        c1 = center(src)
        c2 = center(dst)
        style = "<|-|>" if double else "-|>"
        ls = "--" if dashed else "-"
        if wps:
            pts = [c1] + [to_mpl(w) for w in wps]
            ax.plot([p[0] for p in pts], [p[1] for p in pts],
                    ls=ls, color="#555555", lw=1.4, zorder=0)
            arrow = FancyArrowPatch(
                pts[-1], c2, arrowstyle=style, mutation_scale=14, linewidth=1.4,
                color="#555555", linestyle=ls, patchB=patches[dst], shrinkB=2, zorder=0,
            )
            ax.add_patch(arrow)
            mx, my = to_mpl(lpos)
        else:
            arrow = FancyArrowPatch(
                c1, c2, arrowstyle=style, mutation_scale=14, linewidth=1.4,
                color="#555555", linestyle=ls, patchA=patches[src], patchB=patches[dst],
                shrinkA=2, shrinkB=2, zorder=0,
            )
            ax.add_patch(arrow)
            mx, my = (c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2

        ax.text(
            mx, my, label, ha="center", va="center", fontsize=8, color="#1a1a1a", zorder=6,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9),
        )

    out = os.path.join(os.path.dirname(__file__), "architecture.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    print("wrote", out)


if __name__ == "__main__":
    main()
