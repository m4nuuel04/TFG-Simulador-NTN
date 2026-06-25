from __future__ import annotations

from pathlib import Path
from math import asin, cos, radians, sin, sqrt

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Polygon, Patch
from matplotlib.widgets import CheckButtons

from load_ntn import NTNGraph


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
SURFACE_CSV = DATA_DIR / "superficie_prueba.csv"
ZONES_CSV = DATA_DIR / "superficie_zonas.csv"
STAGE_CSV = DATA_DIR / "stage_oficial.csv"
HAPS_COVERAGE_KM = 20.0
UAV_COVERAGE_KM = 1.0


def load_surface_points(csv_path: Path) -> list[tuple[float, float]]:
    import csv

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        points: list[tuple[float, float]] = []
        for row in reader:
            points.append((float(row["x"]), float(row["y"])))
    return points


def compute_bounds(surface_points: list[tuple[float, float]], graph: NTNGraph) -> tuple[float, float, float, float]:
    xs = [x for x, _ in surface_points] + [node.x for node in graph.nodes.values()]
    ys = [y for _, y in surface_points] + [node.y for node in graph.nodes.values()]
    return min(xs), max(xs), min(ys), max(ys)


def load_zones(csv_path: Path) -> dict[str, dict]:
    import csv

    zones: dict[str, dict] = {}
    if not csv_path.exists():
        return zones

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            zid = row["zone_id"]
            if zid not in zones:
                zones[zid] = {"name": row["zone_name"], "points": []}
            zones[zid]["points"].append((float(row["x"]), float(row["y"])))
    return zones


def load_stage_trace(csv_path: Path) -> list[tuple[float, float]]:
    import csv

    points: list[tuple[float, float]] = []
    if not csv_path.exists():
        return points

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # accept either x,y or lon,lat
            if "x" in row and "y" in row:
                points.append((float(row["x"]), float(row["y"])))
            elif "lon" in row and "lat" in row:
                points.append((float(row["lon"]), float(row["lat"])))
    return points


def km_to_degree_spans(latitude: float, radius_km: float) -> tuple[float, float]:
    latitude_span = radius_km / 110.574
    longitude_scale = max(cos(radians(latitude)), 0.01)
    longitude_span = radius_km / (111.320 * longitude_scale)
    return longitude_span, latitude_span


def distance_km(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    earth_radius_km = 6371.0
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = sin(delta_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    return 2 * earth_radius_km * asin(min(1.0, sqrt(a)))


def build_stage_buffer(stage_points: list[tuple[float, float]], width_km: float) -> list[tuple[float, float]]:
    """Create a simple polygon buffer around a polyline of stage_points.

    Uses per-vertex normals computed from neighboring points. This is an
    approximation good enough for visualization in planar km coordinates.
    Returns polygon points (left offsets then reversed right offsets).
    """
    if len(stage_points) < 2:
        return []
    half = width_km / 2.0
    left_offsets: list[tuple[float, float]] = []
    right_offsets: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(stage_points):
        if i == 0:
            x2, y2 = stage_points[i + 1]
            dx, dy = x2 - x, y2 - y
        elif i == len(stage_points) - 1:
            x0, y0 = stage_points[i - 1]
            dx, dy = x - x0, y - y0
        else:
            x0, y0 = stage_points[i - 1]
            x2, y2 = stage_points[i + 1]
            dx, dy = x2 - x0, y2 - y0

        # normal vector (nx, ny) = (-dy, dx) normalized
        norm = ( -dy, dx )
        nx, ny = norm
        mag = (nx * nx + ny * ny) ** 0.5
        if mag == 0:
            nx, ny = 0.0, 0.0
        else:
            nx, ny = nx / mag, ny / mag

        lx = x + nx * half
        ly = y + ny * half
        rx = x - nx * half
        ry = y - ny * half
        left_offsets.append((lx, ly))
        right_offsets.append((rx, ry))

    # build polygon: left offsets then reversed right offsets
    poly = left_offsets + right_offsets[::-1]
    return poly


def add_haps_coverage(ax: plt.Axes, graph: NTNGraph, radius_km: float, units: str = "deg") -> list[Ellipse]:
    """Add HAPS coverage patches.

    If `units` is 'deg', node coordinates are interpreted as geographic degrees
    (lon/lat) and coverage is converted to degree spans. If `units` is 'km',
    coordinates are treated as planar kilometers and coverage is drawn directly
    with radius in km units.
    """
    coverage_patches: list[Ellipse] = []
    for node in graph.nodes.values():
        if node.node_type.upper() not in {"HAPS", "HAP"}:
            continue
        if units == "deg":
            lon_span, lat_span = km_to_degree_spans(node.y, radius_km)
            width = lon_span * 2.0
            height = lat_span * 2.0
        else:
            # units == 'km': assume equal scaling on both axes and draw using km units
            width = radius_km * 2.0
            height = radius_km * 2.0

        coverage = Ellipse(
            (node.x, node.y),
            width=width,
            height=height,
            facecolor="#2f855a",
            edgecolor="#22543d",
            alpha=0.24,
            linewidth=0.6,
            zorder=30,
        )
        ax.add_patch(coverage)
        coverage_patches.append(coverage)
    return coverage_patches


def add_uav_coverage(ax: plt.Axes, graph: NTNGraph, radius_km: float, units: str = "deg") -> list[Ellipse]:
    coverage_patches: list[Ellipse] = []
    for node in graph.nodes.values():
        if node.node_type.upper() != "UAV":
            continue
        if units == "deg":
            lon_span, lat_span = km_to_degree_spans(node.y, radius_km)
            width = lon_span * 2.0
            height = lat_span * 2.0
        else:
            width = radius_km * 2.0
            height = radius_km * 2.0

        coverage = Ellipse(
            (node.x, node.y),
            width=width,
            height=height,
            facecolor="#feb2b2",
            edgecolor="#c53030",
            alpha=0.22,
            linewidth=0.5,
            zorder=28,
        )
        ax.add_patch(coverage)
        coverage_patches.append(coverage)
    return coverage_patches


def build_view(no_show: bool = False, out_path: Path | None = None, units: str = "deg") -> None:
    surface_points = load_surface_points(SURFACE_CSV)
    graph = NTNGraph.from_csvs()

    if len(surface_points) < 3:
        raise ValueError("La superficie debe tener al menos 3 puntos")

    zones = load_zones(ZONES_CSV)
    stage_points = load_stage_trace(STAGE_CSV)

    all_xs = [x for x, _ in surface_points]
    all_ys = [y for _, y in surface_points]
    for zone in zones.values():
        for x, y in zone["points"]:
            all_xs.append(x)
            all_ys.append(y)
    for x, y in stage_points:
        all_xs.append(x)
        all_ys.append(y)

    span_x = max(all_xs) - min(all_xs)
    span_y = max(all_ys) - min(all_ys)
    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)
    padding_x = max(span_x * 0.12, 0.35)
    padding_y = max(span_y * 0.12, 0.35)

    # Auto-detect units: if user left default 'deg' but coordinate span is small,
    # assume coordinates are km (1 unit = 1 km)
    auto_units = units
    if units == "deg":
        if (max_x - min_x) < 500 and (max_y - min_y) < 500:
            auto_units = "km"
            print("Note: coordinate spans are small — auto-switching to units='km' for visualization")

    fig, ax = plt.subplots(figsize=(15, 10), dpi=120)
    try:
        fig.canvas.manager.set_window_title("Vista NTN")
    except Exception:
        # some backends (Agg) don't have a GUI manager
        pass

    polygon = Polygon(surface_points, closed=True, facecolor="#d9ecff", edgecolor="#2b6cb0", linewidth=2)
    ax.add_patch(polygon)

    # draw zones (if present)
    zone_proxies = []
    zone_artists = []
    zone_colors = ["#f6ad55", "#feb2b2", "#bee3f8", "#c6f6d5", "#d6bcfa"]
    for i, (zid, zinfo) in enumerate(zones.items()):
        # Treat CIRCUIT specially: the circuit corresponds to the stage trace (red line).
        if zid == "ZCIR" or zinfo.get("name", "").upper().startswith("CIRCUIT"):
            # skip polygon creation for circuit; it will be represented by the stage trace
            continue
        pts = zinfo["points"]
        if len(pts) < 3:
            continue
        zpoly = Polygon(pts, closed=True, facecolor=zone_colors[i % len(zone_colors)], edgecolor="#444444", alpha=0.45)
        ax.add_patch(zpoly)
        zone_proxies.append((zinfo["name"], zpoly))
        zone_artists.append(zpoly)

    stage_artist = None
    stage_buffer_artist = None
    if len(stage_points) >= 2:
        xs = [p[0] for p in stage_points]
        ys = [p[1] for p in stage_points]
        (stage_artist,) = ax.plot(xs, ys, color="#e53e3e", linewidth=2.4, label="Etapa oficial más larga", zorder=2)

        # if units==km, draw a 1 km wide buffer polygon around the stage so it
        # appears as an area representing the circuit
        if auto_units == "km":
            try:
                buf = build_stage_buffer(stage_points, width_km=1.0)
                if buf:
                    stage_buffer_artist = Polygon(buf, closed=True, facecolor="#fca5a5", edgecolor="#e53e3e", alpha=0.45, zorder=1)
                    ax.add_patch(stage_buffer_artist)
            except Exception:
                # fail silently and keep the line if buffer creation fails
                stage_buffer_artist = None

    drawn_edges: set[tuple[str, str]] = set()
    edge_artists = []
    for node in graph.nodes.values():
        for neighbor_id in node.neighbors:
            edge_key = tuple(sorted((node.node_id, neighbor_id)))
            if edge_key in drawn_edges:
                continue

            neighbor = graph.nodes[neighbor_id]
            (edge_line,) = ax.plot(
                [node.x, neighbor.x],
                [node.y, neighbor.y],
                color="#666666",
                linewidth=1.4,
                alpha=0.75,
                zorder=1,
            )
            edge_artists.append(edge_line)
            drawn_edges.add(edge_key)

    node_artists = []
    node_label_artists = []
    for node in graph.nodes.values():
        node_type = node.node_type.upper()
        if node_type in {"HAPS", "HAP"}:
            color = "#2f855a"
            size = 42
        else:
            color = "#d64545"
            size = 12

        scatter = ax.scatter(node.x, node.y, s=size, c=color, edgecolors="none", alpha=0.82, zorder=3)
        node_artists.append(scatter)

        if node_type in {"HAPS", "HAP"}:
            label = ax.text(node.x + 0.08, node.y + 0.08, node.node_id, fontsize=10, ha="left", va="bottom")
            node_label_artists.append(label)

    # (Auto-detection moved up to draw buffer correctly)

    # coverage radii may be adjusted by CLI flags set via globals; fall back to constants
    haps_radius = globals().get("VIZ_HAPS_COVERAGE", HAPS_COVERAGE_KM)
    uav_radius = globals().get("VIZ_UAV_COVERAGE", UAV_COVERAGE_KM)
    coverage_scale = globals().get("VIZ_COVERAGE_SCALE", 1.0)

    coverage_artists = add_haps_coverage(ax, graph, haps_radius * coverage_scale, units=auto_units)
    uav_coverage_artists = add_uav_coverage(ax, graph, uav_radius * coverage_scale, units=auto_units)

    ax.set_title("Etapa oficial única y red NTN", fontsize=22)
    ax.set_xlabel("x (km)" if auto_units == "km" else "x", fontsize=18)
    ax.set_ylabel("y (km)" if auto_units == "km" else "y", fontsize=18)
    ax.set_xlim(min_x - padding_x, max_x + padding_x)
    ax.set_ylim(min_y - padding_y, max_y + padding_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_anchor("C")
    ax.grid(True, linestyle="--", alpha=0.35)

    drone_proxy = plt.Line2D([], [], marker="o", color="w", markerfacecolor="#d64545", markeredgecolor="black", markersize=12, label="UAV")
    haps_proxy = plt.Line2D([], [], marker="o", color="w", markerfacecolor="#2f855a", markeredgecolor="black", markersize=12, label="HAPS")
    link_proxy = plt.Line2D([], [], color="#666666", linewidth=1.4, label="Conexión")

    # build legend entries
    coverage_proxy = plt.Line2D([], [], color="#2f855a", alpha=0.2, linewidth=8, label="Cobertura HAPS 20 km")
    coverage_uav_proxy = Patch(facecolor="#feb2b2", edgecolor="#c53030", label="Cobertura UAV 1 km", alpha=0.18)
    handles = [drone_proxy, haps_proxy, link_proxy, coverage_proxy, coverage_uav_proxy]
    # add zone legend entries (polygons)
    for zname, zp in zone_proxies:
        try:
            face = zp.get_facecolor()
        except Exception:
            face = "#888888"
        alpha = zp.get_alpha() if hasattr(zp, "get_alpha") else None
        handles.append(Patch(facecolor=face, edgecolor="#444444", label=zname, alpha=alpha))

    # If circuit zone exists in the zones dataset, add the stage (red line) as its legend entry
    if any(zid == "ZCIR" or zinfo.get("name", "").upper().startswith("CIRCUIT") for zid, zinfo in zones.items()):
        # prefer showing the circuit as an area if we drew a buffer
        if stage_buffer_artist is not None:
            handles.append(Patch(facecolor="#fca5a5", edgecolor="#e53e3e", label="CIRCUIT", alpha=0.45))
        elif stage_artist is not None:
            handles.append(plt.Line2D([], [], color="#e53e3e", linewidth=2.4, label="CIRCUIT"))
        else:
            handles.append(plt.Line2D([], [], color="#e53e3e", linewidth=2.4, label="Etapa oficial más larga"))
    else:
        handles.append(plt.Line2D([], [], color="#e53e3e", linewidth=2.4, label="Etapa oficial más larga"))

    fig.legend(handles=handles, loc="center left", bbox_to_anchor=(0.80, 0.5), frameon=True, fontsize=16, title="Leyenda")
    
    # Removed interactive CheckButtons for non-interactive output compatibility

    if no_show:
        # save to file if requested
        if out_path is None:
            out_path = BASE_DIR.parent / "outputs" / "visualization.png"
        # Ensure outputs directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor='white', transparent=False)
        print(f"Saved visualization to {out_path}")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Visualizar NTN with optional stage traces and zones")
    parser.add_argument("--no-show", action="store_true", help="Do not call plt.show(); save image and exit")
    parser.add_argument("--out", help="Output image file when --no-show is set")
    parser.add_argument("--units", choices=["deg", "km"], default="deg", help="Coordinate units: 'deg' for lon/lat degrees, 'km' for planar kilometers")
    parser.add_argument("--haps-coverage", type=float, default=None, help="Visual HAPS coverage radius (km) for drawing")
    parser.add_argument("--uav-coverage", type=float, default=None, help="Visual UAV coverage radius (km) for drawing")
    parser.add_argument("--coverage-scale", type=float, default=1.0, help="Multiplier to apply to coverage radii for visibility")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else None
    # export chosen visualization settings into module globals that build_view will pick up
    if args.haps_coverage is not None:
        globals()["VIZ_HAPS_COVERAGE"] = args.haps_coverage
    if args.uav_coverage is not None:
        globals()["VIZ_UAV_COVERAGE"] = args.uav_coverage
    globals()["VIZ_COVERAGE_SCALE"] = args.coverage_scale

    build_view(no_show=args.no_show, out_path=out_path, units=args.units)