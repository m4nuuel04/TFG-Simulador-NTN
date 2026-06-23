from pathlib import Path
import csv
import math
from collections import defaultdict

import argparse

from matplotlib.path import Path as MplPath

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
SURFACE_CSV = DATA_DIR / "superficie_prueba.csv"
NODOS_CSV = DATA_DIR / "nodos_ntn.csv"


def read_surface(csv_path: Path):
    pts = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            pts.append((float(r["x"]), float(r["y"])))
    return pts


def generate_grid(minx, maxx, miny, maxy, step):
    xs = []
    x = minx
    while x <= maxx + 1e-9:
        xs.append(round(x, 6))
        x += step
    ys = []
    y = miny
    while y <= maxy + 1e-9:
        ys.append(round(y, 6))
        y += step
    for xi in xs:
        for yi in ys:
            yield (xi, yi)


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def greedy_set_cover(candidates, points, radius):
    """Greedy set cover: returns list of selected candidate indices."""
    # precompute covered indices per candidate
    covered_by = []
    for c in candidates:
        covered = set(i for i, p in enumerate(points) if euclid(c, p) <= radius + 1e-9)
        covered_by.append(covered)

    uncovered = set(range(len(points)))
    selected = []
    # greedy loop
    while uncovered:
        best_idx = None
        best_cov = set()
        best_count = 0
        for i, cov in enumerate(covered_by):
            if not cov:
                continue
            count = len(cov & uncovered)
            if count > best_count:
                best_count = count
                best_cov = cov
                best_idx = i
        if best_idx is None:
            # cannot cover remaining points
            break
        selected.append(best_idx)
        uncovered -= best_cov

    return selected, uncovered


def main():
    parser = argparse.ArgumentParser(description="Generate NTN nodes (HAPS + UAV) to fully cover the surface")
    parser.add_argument("--haps-radius", type=float, default=20.0, help="HAPS coverage radius in km")
    parser.add_argument("--uav-radius", type=float, default=1.0, help="UAV coverage radius in km")
    parser.add_argument("--grid-step", type=float, default=1.0, help="Grid sampling step in km for checking coverage and UAV candidates")
    parser.add_argument("--haps-step", type=float, default=5.0, help="Candidate step for HAPS placement (km)")
    parser.add_argument("--out", type=str, default=str(NODOS_CSV), help="Output CSV path (will overwrite)")
    args = parser.parse_args()

    surface = read_surface(SURFACE_CSV)
    if not surface:
        raise SystemExit("Surface polygon empty")

    # bounding box
    xs = [p[0] for p in surface]
    ys = [p[1] for p in surface]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    # sample points inside surface at grid-step resolution
    poly_path = MplPath(surface)
    sample_pts = []
    for gx, gy in generate_grid(minx, maxx, miny, maxy, args.grid_step):
        if poly_path.contains_point((gx, gy)):
            sample_pts.append((gx, gy))

    if not sample_pts:
        raise SystemExit("No sample points inside surface; check grid step or surface polygon")

    print(f"Sample points inside surface: {len(sample_pts)}")

    # HAPS candidates on coarser grid
    h_candidates = [c for c in generate_grid(minx, maxx, miny, maxy, args.haps_step) if poly_path.contains_point(c)]
    print(f"HAPS candidates: {len(h_candidates)}")

    # UAV candidates: use finer grid equal to grid_step
    u_candidates = [c for c in generate_grid(minx, maxx, miny, maxy, args.grid_step) if poly_path.contains_point(c)]
    print(f"UAV candidates: {len(u_candidates)}")

    # Greedy cover for HAPS
    print("Selecting HAPS (greedy set cover)...")
    h_selected_idx, h_uncovered = greedy_set_cover(h_candidates, sample_pts, args.haps_radius)
    h_selected = [h_candidates[i] for i in h_selected_idx]
    print(f"HAPS selected: {len(h_selected)}, uncovered sample points after HAPS: {len(h_uncovered)}")

    # Greedy cover for UAV
    print("Selecting UAVs (greedy set cover)...")
    u_selected_idx, u_uncovered = greedy_set_cover(u_candidates, sample_pts, args.uav_radius)
    u_selected = [u_candidates[i] for i in u_selected_idx]
    print(f"UAVs selected: {len(u_selected)}, uncovered sample points after UAV: {len(u_uncovered)}")

    if h_uncovered:
        print("Warning: some sample points are not covered by HAPS — consider reducing grid step or increasing candidate density")
    if u_uncovered:
        print("Warning: some sample points are not covered by UAVs — consider reducing grid step")

    # Build CSV rows
    rows = []
    hid = 1
    for x, y in h_selected:
        rows.append({
            "node_id": f"HAPS-{hid:03d}",
            "node_type": "HAPS",
            "x": f"{x:.6f}",
            "y": f"{y:.6f}",
            "cpu_capacity_ghz": f"32.00",
            "mem_capacity_gib": f"64.00",
            "bandwidth_capacity_mbps": f"300.00",
            "storage_capacity_gb": f"512.00",
        })
        hid += 1

    uid = 1
    for x, y in u_selected:
        rows.append({
            "node_id": f"UAV-{uid:03d}",
            "node_type": "UAV",
            "x": f"{x:.6f}",
            "y": f"{y:.6f}",
            "cpu_capacity_ghz": f"8.00",
            "mem_capacity_gib": f"16.00",
            "bandwidth_capacity_mbps": f"120.00",
            "storage_capacity_gb": f"64.00",
        })
        uid += 1

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["node_id", "node_type", "x", "y", "cpu_capacity_ghz", "mem_capacity_gib", "bandwidth_capacity_mbps", "storage_capacity_gb"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Wrote {len(rows)} nodes to {out_path}")
    print(f"HAPS: {len(h_selected)}, UAV: {len(u_selected)}")


if __name__ == "__main__":
    main()
