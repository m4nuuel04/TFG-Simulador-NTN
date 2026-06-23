#!/usr/bin/env python3
"""
Greedy placement: place microservice replicas as close as possible to the zones
from which they are called, while respecting node capacities and ensuring every
node hosts at least one microservice when possible.

Outputs a placements CSV and visual report like the random placer.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path

from load_microservices import MicroservicesData
from load_ntn import NTNGraph

# Reuse helpers from random_placement where convenient
import random_placement as rp

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR.parent / "outputs"
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "placements_greedy.csv"


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def dist_point_to_segment(px, py, x1, y1, x2, y2):
    # project p onto segment
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    projx = x1 + t * dx
    projy = y1 + t * dy
    return math.hypot(px - projx, py - projy)


def distance_point_to_polygon(px, py, poly):
    if point_in_poly(px, py, poly):
        return 0.0
    # compute min distance to edges
    best = float('inf')
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        d = dist_point_to_segment(px, py, x1, y1, x2, y2)
        if d < best:
            best = d
    return best


def load_zone_polygons(zones_csv: Path):
    polys = {}
    with zones_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        by_zone = defaultdict(list)
        for r in rows:
            zid = r.get('zone_id')
            if not zid:
                continue
            try:
                order = int(r.get('point_order') or 0)
            except Exception:
                order = 0
            x = float(r.get('x') or 0)
            y = float(r.get('y') or 0)
            by_zone[zid].append((order, (x, y)))
        for zid, pts in by_zone.items():
            pts_sorted = [p for _, p in sorted(pts, key=lambda t: t[0])]
            polys[zid] = pts_sorted
    return polys


def greedy_place(graph: NTNGraph, services: list[dict], zone_polys: dict[str, list[tuple[float, float]]], seed: int | None = None) -> rp.PlacementResult:
    rng = random.Random(seed)
    node_states = rp.build_node_states(graph)
    node_count = len(node_states)
    node_map = {ns.node_id: ns for ns in node_states}

    # precompute node coordinates
    node_coords = {n.node_id: (n.x, n.y) for n in graph.nodes.values()}

    # compute distance matrix: node -> service(zone) distance as needed
    def svc_zone_distance(node_id, svc):
        zid = svc.get('zone_id', '')
        if zid and zid in zone_polys:
            poly = zone_polys[zid]
            x, y = node_coords[node_id]
            return distance_point_to_polygon(x, y, poly)
        # if no zone, fallback to zero distance
        return 0.0

    assignments: list[rp.PlacementRecord] = []
    unplaced_replicas: list[tuple[str, int]] = []
    requested_replicas = 0

    # mutable service list with remaining count
    svc_list = []
    for svc in services:
        s = dict(svc)
        s['placed'] = 0
        svc_list.append(s)
        requested_replicas += s['requested_replicas']

    # Phase 1: ensure every node has at least one microservice
    node_order = list(node_map.keys())
    rng.shuffle(node_order)
    for nid in node_order:
        node = node_map[nid]
        # find candidates that fit and have remaining replicas and not already hosted
        candidates = [s for s in svc_list if s['placed'] < s['requested_replicas'] and s['service_id'] not in node.hosted_services and node.can_host(s)]
        if not candidates:
            continue
        # choose candidate closest to its zone (greedy)
        candidates.sort(key=lambda s: svc_zone_distance(nid, s))
        chosen = candidates[0]
        node.place(chosen)
        chosen['placed'] += 1
        assignments.append(rp.PlacementRecord(chosen['app_id'], chosen['app_name'], chosen['service_id'], chosen['service_name'], chosen['placed'], nid))

    # Phase 2: for each service, place remaining replicas on nearest nodes to zone
    # sort services by remaining replicas descending to place large ones first
    services_by_remaining = sorted(svc_list, key=lambda s: (s['requested_replicas'] - s['placed']), reverse=True)
    for svc in services_by_remaining:
        while svc['placed'] < svc['requested_replicas']:
            # build list of candidate nodes sorted by distance to svc zone
            candidates = []
            for nid, node in node_map.items():
                if svc['service_id'] in node.hosted_services:
                    continue
                if not node.can_host(svc):
                    continue
                d = svc_zone_distance(nid, svc)
                candidates.append((d, nid))
            if not candidates:
                # cannot place remaining replicas
                unplaced_replicas.append((svc['service_id'], svc['placed'] + 1))
                break
            candidates.sort(key=lambda t: t[0])
            _, chosen_nid = candidates[0]
            node = node_map[chosen_nid]
            node.place(svc)
            svc['placed'] += 1
            assignments.append(rp.PlacementRecord(svc['app_id'], svc['app_name'], svc['service_id'], svc['service_name'], svc['placed'], chosen_nid))

    return rp.PlacementResult(assignments=assignments, unplaced_replicas=unplaced_replicas, requested_replicas=requested_replicas, placed_replicas=len(assignments))


def main():
    # Ensure outputs directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description='Greedy microservice placement near caller zones')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument('--plot-out', type=Path, default=OUTPUT_DIR / 'placements_greedy.png')
    parser.add_argument('--node-report-out', type=Path, default=OUTPUT_DIR / 'placements_greedy_by_node.md')
    args = parser.parse_args()

    graph = NTNGraph.from_csvs()
    zonified = Path('data') / 'microservicios_zonificados.csv'
    if zonified.exists():
        ms_data = MicroservicesData(csv_path=zonified)
    else:
        ms_data = MicroservicesData()

    services = [rp.normalize_service(row, len(graph.nodes)) for row in ms_data.get_all_data().to_dict('records')]

    zone_polys = load_zone_polygons(BASE_DIR.parent / 'data' / 'superficie_zonas.csv')

    result = greedy_place(graph, services, zone_polys, seed=args.seed)

    rp.save_assignments_csv(result.assignments, args.out)
    rp.save_placement_plot(graph, result, args.plot_out)
    rp.save_node_report_markdown(rp.build_node_assignments(result), args.node_report_out)

    print('GREEDY PLACEMENT SUMMARY')
    print(f'Nodos disponibles: {len(graph.nodes)}')
    print(f'Replicas solicitadas: {result.requested_replicas}')
    print(f'Replicas colocadas: {result.placed_replicas}')
    print(f'Replicas no colocadas: {len(result.unplaced_replicas)}')


if __name__ == '__main__':
    main()
