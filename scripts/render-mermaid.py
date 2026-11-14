"""Render the two report diagrams via mermaid.ink and stitch to page-sized PNGs.

Long vertical chains are rendered as separate strips and stitched side by
side with PIL so both figures fit a portrait A4 page.
"""

import base64
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

DONE = "fill:#c9e7d8,stroke:#2f8f8c,stroke-width:2px,color:#12312f"
PENDING = "fill:#e4e4e4,stroke:#9a9a9a,stroke-width:2px,color:#555555"


def strip(steps):
    """One vertical strip: [(label, phase, done), ...] -> mermaid source."""
    lines = ["flowchart TD"]
    for index, (label, phase, _done) in enumerate(steps):
        lines.append(f'    N{index}["{label}<br/>{phase}"]')
    for index in range(len(steps) - 1):
        lines.append(f"    N{index} --> N{index + 1}")
    for index, (_, _, done) in enumerate(steps):
        style = DONE if done else PENDING
        lines.append(f"    style N{index} {style}")
    return "\n".join(lines)


def render(name: str, code: str, width: int) -> Image.Image:
    encoded = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/img/{encoded}?type=png&width={width}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    path = OUT / name
    path.write_bytes(data)
    image = Image.open(path)
    print("rendered", path, image.size)
    return image


def stitch(images, out_name: str, connector: str | None = None) -> Path:
    """Place strips side by side; draw the gutter connector + optional label."""
    gap = 90 if connector else 60
    height = max(image.height for image in images) + 20
    total = sum(image.width for image in images) + gap * (len(images) - 1) + 40
    canvas = Image.new("RGB", (total, height), "white")
    x = 20
    for index, image in enumerate(images):
        canvas.paste(image, (x, 10))
        x += image.width
        if index < len(images) - 1:
            draw = ImageDraw.Draw(canvas)
            mid = height // 2
            start, end = x + 8, x + gap - 8
            draw.line([(start, mid), (end, mid)], fill="#2f8f8c", width=4)
            # Arrow head pointing right.
            draw.polygon([(end, mid - 7), (end, mid + 7), (end + 8, mid)], fill="#2f8f8c")
            if connector:
                try:
                    font = ImageFont.truetype("arialbd.ttf", 22)
                except OSError:
                    font = ImageFont.load_default()
                text_width = draw.textlength(connector, font=font)
                draw.text(
                    ((start + end) / 2 - text_width / 2, mid - 42),
                    connector,
                    fill="#4a3a10",
                    font=font,
                )
            x += gap
    path = OUT / out_name
    canvas.save(path)
    print("stitched", path, canvas.size)
    return path


# ── Figure 1: 14-step work flow as three columns of five-ish steps ───────────
COLUMNS = [
    [
        ("1. Requirements", "Phase 0", True),
        ("2. Design", "Phase 0", True),
        ("3. Database", "Phase 1", True),
        ("4. Auth and roles", "Phase 2", True),
        ("5. Realtime backbone", "Phase 3", True),
    ],
    [
        ("6. Domain APIs", "Phase 4", True),
        ("7. AI modules", "Phase 5", True),
        ("8. Tracer simulator", "Phase 6", True),
        ("9. Landing page", "Phase 7", True),
        ("10. Sign in / register", "Phase 8", True),
    ],
    [
        ("11. Dashboards", "Phase 9", True),
        ("12. PWA", "Phase 10", False),
        ("13. Security and testing", "Phase 11", False),
        ("14. Deployment", "Phase 12", False),
    ],
]
strips = [render(f"fig-wf-col{i}.png", strip(steps), 560) for i, steps in enumerate(COLUMNS)]
stitch(strips, "fig-workflow.png")

# ── Figure 2: system flow, split at the Employer -> PPI edge ────────────────
PART_A = """flowchart TD
    P["Training Provider<br/>certifies trainee"] -->|"TRAINEE_CERTIFIED"| T["Trainee<br/>grants consent and<br/>answers the tracer"]
    T -->|"FOLLOWUP_RESPONDED"| E["Employer<br/>verifies the claim<br/>(dual signal)"]
    style P fill:#c9e7d8,stroke:#2f8f8c,stroke-width:2px,color:#12312f
    style T fill:#c9e7d8,stroke:#2f8f8c,stroke-width:2px,color:#12312f
    style E fill:#c9e7d8,stroke:#2f8f8c,stroke-width:2px,color:#12312f
"""
PART_B = """flowchart TD
    V["PPI recalculated<br/>for the centre"] -->|"PPI_RECALCULATED"| A["Admin dashboard<br/>updates live"]
    style V fill:#fbe6b8,stroke:#c99a1e,stroke-width:2px,color:#4a3a10
    style A fill:#c9e7d8,stroke:#2f8f8c,stroke-width:2px,color:#12312f
"""
part_a = render("fig-sys-a.png", PART_A, 560)
part_b = render("fig-sys-b.png", PART_B, 560)
stitch([part_a, part_b], "fig-systemflow.png", connector="VERIFICATION_COMPLETE")
