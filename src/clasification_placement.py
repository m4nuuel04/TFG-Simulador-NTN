#!/usr/bin/env python3
"""
Greedy tiered placement:
- Classify services: 
  - Strict latency (<= 500ms) prefers UAV.
  - Heavy compute (HIGH intensity or >=1.0 CPU) prefers HAPS.
  - Others prefer UAV.
- Sort services by latency_max_ms ascending so strict ones are placed first.
- Phase 1: At least one service per node, matching node preference if possible.
- Phase 2: Place remaining replicas greedily (closest to zone) prioritizing preferred node type, fallback to any.
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

import random_placement as rp
from greedy_placement import point_in_poly, dist_point_to_segment, distance_point_to_polygon, load_zone_polygons

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR.parent / "outputs"
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "placements_clasification.csv"

def determine_preferred_type(svc: dict) -> str:
    latency = rp.parse_float(svc.get('latency_max_ms'), float('inf'))
    if latency <= 500:
        return 'UAV'
    
    cpu_demand = svc.get('cpu_demand', 0.0)
    intensity = str(svc.get('compute_intensity', '')).upper()
    if intensity == 'HIGH' or cpu_demand >= 1.0:
        return 'HAPS'
        
    return 'UAV'

def clasification_place(graph: NTNGraph, services: list[dict], zone_polys: dict[str, list[tuple[float, float]]], seed: int | None = None) -> rp.PlacementResult:
    rng = random.Random(seed)
    node_states = rp.build_node_states(graph)
    node_count = len(node_states)
    node_map = {ns.node_id: ns for ns in node_states}

    node_coords = {n.node_id: (n.x, n.y) for n in graph.nodes.values()}

    def svc_zone_distance(node_id, svc):
        zid = svc.get('zone_id', '')
        if zid and zid in zone_polys:
            poly = zone_polys[zid]
            x, y = node_coords[node_id]
            return distance_point_to_polygon(x, y, poly)
        return 0.0

    assignments: list[rp.PlacementRecord] = []
    unplaced_replicas: list[tuple[str, int]] = []
    requested_replicas = 0

    svc_list = []
    for svc in services:
        s = dict(svc)
        s['placed'] = 0
        s['preferred_node_type'] = determine_preferred_type(s)
        # Parse latency for sorting
        s['sort_latency'] = rp.parse_float(s.get('latency_max_ms'), float('inf'))
        svc_list.append(s)
        requested_replicas += s['requested_replicas']

    # Phase 1: ensure every node has at least one microservice
    node_order = list(node_map.keys())
    rng.shuffle(node_order)
    for nid in node_order:
        node = node_map[nid]
        
        # Priority 1: fit node type preference AND sort by latency
        candidates = [s for s in svc_list if s['placed'] < s['requested_replicas'] and s['service_id'] not in node.hosted_services and node.can_host(s)]
        if not candidates:
            continue
            
        # Try to find one matching node preference
        pref_candidates = [s for s in candidates if s['preferred_node_type'] == node.node_type]
        
        if pref_candidates:
            # Sort by latency (ascending) and then by distance to zone
            pref_candidates.sort(key=lambda s: (s['sort_latency'], svc_zone_distance(nid, s)))
            chosen = pref_candidates[0]
        else:
            # Fallback to any fitting candidate
            candidates.sort(key=lambda s: (s['sort_latency'], svc_zone_distance(nid, s)))
            chosen = candidates[0]
            
        node.place(chosen)
        chosen['placed'] += 1
        assignments.append(rp.PlacementRecord(chosen['app_id'], chosen['app_name'], chosen['service_id'], chosen['service_name'], chosen['placed'], nid))

    # Phase 2: place remaining replicas
    # Sort services by latency ascending, then by remaining replicas descending
    services_to_place = sorted(svc_list, key=lambda s: (s['sort_latency'], -(s['requested_replicas'] - s['placed'])))
    
    for svc in services_to_place:
        while svc['placed'] < svc['requested_replicas']:
            candidates = []
            for nid, node in node_map.items():
                if svc['service_id'] in node.hosted_services:
                    continue
                if not node.can_host(svc):
                    continue
                d = svc_zone_distance(nid, svc)
                is_pref = 0 if node.node_type == svc['preferred_node_type'] else 1
                candidates.append((is_pref, d, nid))
                
            if not candidates:
                unplaced_replicas.append((svc['service_id'], svc['placed'] + 1))
                break
                
            # Sort by is_pref (0 first), then distance
            candidates.sort(key=lambda t: (t[0], t[1]))
            _, _, chosen_nid = candidates[0]
            node = node_map[chosen_nid]
            node.place(svc)
            svc['placed'] += 1
            assignments.append(rp.PlacementRecord(svc['app_id'], svc['app_name'], svc['service_id'], svc['service_name'], svc['placed'], chosen_nid))

    return rp.PlacementResult(assignments=assignments, unplaced_replicas=unplaced_replicas, requested_replicas=requested_replicas, placed_replicas=len(assignments))

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument('--plot-out', type=Path, default=OUTPUT_DIR / 'placements_clasification.png')
    parser.add_argument('--node-report-out', type=Path, default=OUTPUT_DIR / 'placements_clasification_by_node.md')
    args = parser.parse_args()

    graph = NTNGraph.from_csvs()
    zonified = Path('data') / 'microservicios_zonificados.csv'
    if zonified.exists():
        ms_data = MicroservicesData(csv_path=zonified)
    else:
        ms_data = MicroservicesData()

    raw_services = ms_data.get_all_data().to_dict('records')
    services = []
    for row in raw_services:
        s = rp.normalize_service(row, len(graph.nodes))
        s['latency_max_ms'] = row.get('latency_max_ms')
        s['compute_intensity'] = row.get('compute_intensity')
        services.append(s)

    zone_polys = load_zone_polygons(BASE_DIR.parent / 'data' / 'superficie_zonas.csv')

    result = clasification_place(graph, services, zone_polys, seed=args.seed)

    rp.save_assignments_csv(result.assignments, args.out)
    rp.save_placement_plot(graph, result, args.plot_out)
    rp.save_node_report_markdown(rp.build_node_assignments(result), args.node_report_out)

    print('CLASIFICATION PLACEMENT SUMMARY')
    print(f'Nodos disponibles: {len(graph.nodes)}')
    print(f'Replicas solicitadas: {result.requested_replicas}')
    print(f'Replicas colocadas: {result.placed_replicas}')
    print(f'Replicas no colocadas: {len(result.unplaced_replicas)}')


if __name__ == '__main__':
    main()
