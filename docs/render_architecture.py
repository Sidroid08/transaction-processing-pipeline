"""Render docs/architecture.drawio to a PNG that mirrors the same diagram.

Coordinates are taken directly from the mxGeometry values in architecture.drawio
so the PNG matches the editable diagram. Run: python docs/render_architecture.py
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

MAXY = 560  # drawio y grows downward; flip into matplotlib's upward y-axis.

# fill, stroke
BLUE = ("#dae8fc", "#6c8ebf")
GREEN = ("#d5e8d4", "#82b366")
RED = ("#f8cecc", "#b85450")
ORANGE = ("#ffe6cc", "#d79b00")
PURPLE = ("#e1d5e7", "#9673a6")
YELLOW = ("#fff2cc", "#d6b656")
LLMBLUE = ("#d4e1f5", "#6c8ebf")

# id -> (x, y, w, h, label, colors, dashed)
BOXES = {
    "client": (60, 120, 140, 70, "Client\n(curl / Swagger UI)", BLUE, False),
    "api": (
        280, 100, 220, 120,
        "FastAPI (api)\n\nPOST /jobs/upload\nGET /jobs/{id}/status\nGET /jobs/{id}/results\nGET /jobs?status=",
        GREEN, False,
    ),
    "redis": (600, 60, 180, 80, "Redis\n(Celery broker +\nresult backend)", RED, False),
    "worker": (
        600, 190, 220, 160,
        "Celery Worker\n\na) Clean + dedupe\nb) Anomaly detection\nc) LLM classify (batched)\nd) LLM narrative summary\ne) Retry w/ backoff",
        ORANGE, False,
    ),
    "db": (320, 320, 160, 100, "PostgreSQL\n\njobs / transactions\n/ job_summaries", PURPLE, False),
    "volume": (320, 460, 200, 60, "Shared Volume\n/data/uploads/{job_id}.csv", YELLOW, True),
    "llm": (
        900, 220, 180, 100,
        "LLM Provider\nGemini 1.5 Flash\n(auto-fallback to\nlocal stub)",
        LLMBLUE, False,
    ),
}

# source, target, label, dashed, double-headed
EDGES = [
    ("client", "api", "1. upload CSV", False, False),
    ("api", "volume", "2. save raw CSV", False, False),
    ("api", "db", "3. create Job (pending)", False, False),
    ("api", "redis", "4. enqueue task", False, False),
    ("redis", "worker", "5. dequeue", False, False),
    ("worker", "volume", "6. read CSV", True, False),
    ("worker", "llm", "7. classify + summarise", False, False),
    ("worker", "db", "8. persist results,\nmark completed", False, False),
    ("client", "db", "9. poll status / results", False, True),
]


def rect_xy(x, y, w, h):
    """drawio top-left (x,y,w,h) -> matplotlib lower-left (x, y')."""
    return x, MAXY - y - h, w, h


def center(box):
    x, y, w, h = box[:4]
    return x + w / 2, MAXY - y - h / 2


def main() -> None:
    fig, ax = plt.subplots(figsize=(14, 7.2), dpi=160)
    ax.set_xlim(30, 1110)
    ax.set_ylim(0, 580)
    ax.axis("off")

    ax.text(
        570, 555, "AI-Powered Transaction Processing Pipeline — Architecture",
        ha="center", va="center", fontsize=17, fontweight="bold",
    )

    patches = {}
    for key, (x, y, w, h, label, (fill, stroke), dashed) in BOXES.items():
        rx, ry, rw, rh = rect_xy(x, y, w, h)
        patch = FancyBboxPatch(
            (rx, ry), rw, rh,
            boxstyle="round,pad=2,rounding_size=8",
            linewidth=1.6, edgecolor=stroke, facecolor=fill,
            linestyle="--" if dashed else "-", mutation_aspect=1,
        )
        ax.add_patch(patch)
        patches[key] = patch
        cx, cy = center(BOXES[key])
        ax.text(cx, cy, label, ha="center", va="center", fontsize=9.2, color="#222222")

    for src, dst, label, dashed, double in EDGES:
        c1 = center(BOXES[src])
        c2 = center(BOXES[dst])
        arrow = FancyArrowPatch(
            c1, c2,
            arrowstyle="<|-|>" if double else "-|>",
            mutation_scale=14, linewidth=1.4, color="#555555",
            linestyle="--" if dashed else "-",
            patchA=patches[src], patchB=patches[dst],
            shrinkA=2, shrinkB=2, zorder=0,
        )
        ax.add_patch(arrow)
        mx, my = (c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2
        ax.text(
            mx, my, label, ha="center", va="center", fontsize=8,
            color="#1a1a1a",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85),
        )

    out = os.path.join(os.path.dirname(__file__), "architecture.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    print("wrote", out)


if __name__ == "__main__":
    main()
