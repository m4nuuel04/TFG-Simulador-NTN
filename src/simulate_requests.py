#!/usr/bin/env python3
"""
Simulate requests to microservices from random points within their zones.

For each microservice, performs N requests (default 5). For each request:
- sample a random point inside the microservice's zone polygon (or circuit if allowed)
- find nearest node that hosts a replica of the microservice (from placements CSV)
- compute distance and simple latency model (propagation + processing)

Outputs:
- CSV `data/requests_simulation.csv` with one row per request
- Prints a summary (per-service and overall)
"""
import argparse
import csv
import heapq
import math
import random
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
OUTPUT_DIR = BASE_DIR.parent / "outputs"
NODES_CSV = DATA_DIR / "nodos_ntn.csv"
CONNECTIONS_CSV = DATA_DIR / "conexiones_ntn.csv"
DEFAULT_PLACEMENTS_CSV = OUTPUT_DIR / "placements_random.csv"
ZONED_MS_CSV = DATA_DIR / "microservicios_zonificados.csv"
ZONES_CSV = DATA_DIR / "superficie_zonas.csv"
DEFAULT_OUT_CSV = OUTPUT_DIR / "requests_simulation.csv"
APPS_CSV = DATA_DIR / "aplicaciones.csv"
DEFAULT_APPS_OUT_CSV = OUTPUT_DIR / "app_requests_simulation.csv"


def load_zone_polygons(zones_csv: Path):
    polys = {}
    with zones_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        # group by zone_id and sort by point_order if present
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


def sample_point_in_poly(poly, rng: random.Random):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    for _ in range(10000):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if point_in_poly(x, y, poly):
            return x, y
    raise RuntimeError("Failed to sample point in polygon")


def load_nodes(nodes_csv: Path):
    nodes = {}
    with nodes_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            nid = r['node_id']
            nodes[nid] = {
                'node_type': r.get('node_type'),
                'x': float(r.get('x') or 0),
                'y': float(r.get('y') or 0),
                'cpu_capacity_ghz': float(r.get('cpu_capacity_ghz') or 0.0),
                'mem_capacity_gib': float(r.get('mem_capacity_gib') or 0.0),
                'bandwidth_capacity_mbps': float(r.get('bandwidth_capacity_mbps') or 0.0),
                'storage_capacity_gb': float(r.get('storage_capacity_gb') or 0.0),
            }
    return nodes


def load_placements(placements_csv: Path):
    svc_to_nodes = defaultdict(list)
    with placements_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            svc_to_nodes[r['service_id']].append(r['node_id'])
    return svc_to_nodes


def load_graph(connections_csv: Path):
    graph = defaultdict(dict)
    with connections_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            src = r['source_node_id']
            tgt = r['target_node_id']
            if src == tgt:
                continue
            
            # Peso según tipo de nodo: Si pasa por HAPS, sumamos más latencia
            if src.startswith('HAPS') or tgt.startswith('HAPS'):
                weight = 20.0
            else:
                weight = 1.0
            
            graph[src][tgt] = weight
            graph[tgt][src] = weight  # aseguro que sea bidireccional
    return graph


def dijkstra(graph, start_node, target_nodes, link_usage=None, congestion_penalty=0.0):
    # Returns the minimum path latency, the chosen target node, and the path
    if start_node in target_nodes:
        return 0.0, start_node, [start_node]
    
    pq = [(0.0, start_node)]
    visited = set()
    distances = {start_node: 0.0}
    predecessors = {start_node: None}
    
    while pq:
        dist, current = heapq.heappop(pq)
        
        if current in visited:
            continue
        visited.add(current)
        
        if current in target_nodes:
            path = []
            curr = current
            while curr is not None:
                path.append(curr)
                curr = predecessors.get(curr)
            path.reverse()
            return dist, current, path
            
        for neighbor, base_weight in graph.get(current, {}).items():
            if neighbor not in visited:
                penalty = 0.0
                if link_usage is not None and congestion_penalty > 0:
                    usage = link_usage.get((current, neighbor), 0) + link_usage.get((neighbor, current), 0)
                    penalty = usage * congestion_penalty
                
                new_dist = dist + base_weight + penalty
                if new_dist < distances.get(neighbor, float('inf')):
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))
                
    return float('inf'), None, []


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def simulate(args):
    rng = random.Random(args.seed)

    polys = load_zone_polygons(ZONES_CSV)
    nodes = load_nodes(NODES_CSV)
    graph = load_graph(CONNECTIONS_CSV)
    svc_nodes = load_placements(args.placements)

    # load microservices zonified
    ms_rows = []
    with ZONED_MS_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            ms_rows.append(r)

    out_rows = []
    per_service_stats = defaultdict(list)
    request_id = 0

    # latency model params
    propagation_ms_per_km = 0.4  # round-trip ms per km (phenomenological)
    link_usage = defaultdict(int)
    congestion_penalty = getattr(args, 'congestion_penalty', 0.0)

    for ms in ms_rows:
        service_id = ms['service_id']
        zone_id = ms.get('zone_id', '')
        callable_circuit = str(ms.get('callable_from_circuit', 'NO')).upper() == 'YES'

        if zone_id == '' or zone_id not in polys:
            # skip services without a known polygon
            continue

        poly = polys[zone_id]
        # collect candidate nodes that host this service
        candidate_node_ids = svc_nodes.get(service_id, [])
        if not candidate_node_ids:
            # record failures
            for _ in range(args.requests_per_service):
                request_id += 1
                out_rows.append({
                    'request_id': request_id,
                    'service_id': service_id,
                    'point_x': '', 'point_y': '',
                    'entry_node': '', 'target_node': '', 'target_x': '', 'target_y': '',
                    'path_latency_ms': '', 'propagation_ms': '', 'processing_ms': '', 'total_ms': '', 'status': 'NO_REPLICA'
                })
            continue

        for _ in range(args.requests_per_service):
            request_id += 1
            px, py = sample_point_in_poly(poly, rng)

            # find nearest node among ALL nodes (entry point to network)
            entry_node = None
            nearest_dist = float('inf')
            for nid, n in nodes.items():
                d = euclid((px, py), (n['x'], n['y']))
                if d < nearest_dist:
                    entry_node = nid
                    nearest_dist = d

            if entry_node is None:
                status = 'NO_NODE'
                out_rows.append({
                    'request_id': request_id,
                    'service_id': service_id,
                    'point_x': px, 'point_y': py,
                    'entry_node': '', 'target_node': '', 'target_x': '', 'target_y': '',
                    'path_latency_ms': '', 'propagation_ms': '', 'processing_ms': '', 'total_ms': '', 'status': status
                })
                continue

            # use Dijkstra to find shortest network path to a node with the microservice
            path_latency, target_node, path = dijkstra(graph, entry_node, set(candidate_node_ids), link_usage, congestion_penalty)
            
            if len(path) > 1:
                for i in range(len(path) - 1):
                    link_usage[(path[i], path[i+1])] += 1
                    link_usage[(path[i+1], path[i])] += 1

            if target_node is None:
                status = 'NO_ROUTE'
                out_rows.append({
                    'request_id': request_id,
                    'service_id': service_id,
                    'point_x': px, 'point_y': py,
                    'entry_node': entry_node, 'target_node': '', 'target_x': '', 'target_y': '',
                    'path_latency_ms': '', 'propagation_ms': '', 'processing_ms': '', 'total_ms': '', 'status': status
                })
                continue

            node = nodes[target_node]
            
            # Propagation time: 
            # 1 ms between point and entry_node
            # + path_latency (from Dijkstra)
            
            # Request time (user -> entry node -> target node) with +/- 10% variance
            req_entry_ms = 1.0 * rng.uniform(0.9, 1.1)
            req_path_ms = path_latency * rng.uniform(0.9, 1.1)
            request_ms = req_entry_ms + req_path_ms
            
            # Response time (target node -> entry node -> user) with +/- 10% variance
            resp_path_ms = path_latency * rng.uniform(0.9, 1.1)
            resp_entry_ms = 1.0 * rng.uniform(0.9, 1.1)
            response_ms = resp_path_ms + resp_entry_ms
            
            # Total propagation includes the request sent to the node, and the response returned to the user
            propagation_ms = request_ms + response_ms

            # Processing time: model using service CPU demand vs node CPU capacity and compute_intensity
            try:
                cpu_demand = float(ms.get('cpu_demand') or 0.0)
            except Exception:
                cpu_demand = 0.0
            try:
                node_cpu = float(node.get('cpu_capacity_ghz') or 1.0)
            except Exception:
                node_cpu = 1.0

            intensity = str(ms.get('compute_intensity') or '').upper()
            intensity_factor = 1.0
            if intensity.startswith('HIGH'):
                intensity_factor = 1.0
            elif intensity.startswith('MED'):
                intensity_factor = 0.6
            else:
                intensity_factor = 0.3

            # base processing time proportional to cpu fraction, scaled to milliseconds
            if node_cpu > 0:
                processing_s = (cpu_demand / node_cpu) * intensity_factor * 1.0
            else:
                processing_s = intensity_factor * 1.0
            processing_ms = processing_s * 1000.0

            total_ms = propagation_ms + processing_ms

            # SLO handling
            slo_val = None
            try:
                slo_val = float(ms.get('latency_max_ms')) if ms.get('latency_max_ms') not in (None, '') else None
            except Exception:
                slo_val = None

            slo_violation = False
            orig_total_ms = total_ms
            if slo_val is not None and orig_total_ms > slo_val:
                slo_violation = True
                if args.enforce_slo:
                    total_ms = slo_val

            out_rows.append({
                'request_id': request_id,
                'service_id': service_id,
                'point_x': f"{px:.6f}", 'point_y': f"{py:.6f}",
                'entry_node': entry_node, 'target_node': target_node, 'target_x': f"{node['x']:.6f}", 'target_y': f"{node['y']:.6f}",
                'path_latency_ms': f"{path_latency:.1f}", 'propagation_ms': f"{propagation_ms:.6f}", 'processing_ms': f"{processing_ms:.6f}", 'orig_total_ms': f"{orig_total_ms:.6f}", 'latency_max_ms': (f"{slo_val:.6f}" if slo_val is not None else ''), 'slo_violation': ('YES' if slo_violation else 'NO'), 'total_ms': f"{total_ms:.6f}", 'status': 'OK'
            })

            per_service_stats[service_id].append(total_ms)

    # write CSV
    fieldnames = ['request_id','service_id','point_x','point_y','entry_node','target_node','target_x','target_y','path_latency_ms','propagation_ms','processing_ms','orig_total_ms','latency_max_ms','slo_violation','total_ms','status']
    with args.out.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    # print summary
    total_requests = len(out_rows)
    ok_requests = sum(1 for r in out_rows if r['status']=='OK')
    print(f"Total requests: {total_requests}")
    print(f"Successful: {ok_requests}")
    print(f"Failed: {total_requests - ok_requests}")

    # SLO stats
    violation_count = sum(1 for r in out_rows if r.get('slo_violation') == 'YES')
    if violation_count:
        print(f"SLO violations: {violation_count} ({violation_count/total_requests:.1%})")
    else:
        print("SLO violations: 0")

    # per-service summary
    print("\nPer-service latency (ms):")
    overall = []
    for svc, vals in sorted(per_service_stats.items()):
        if not vals:
            continue
        avg = sum(vals)/len(vals)
        mn = min(vals)
        mx = max(vals)
        overall.extend(vals)
        print(f"  {svc}: avg={avg:.3f} ms, min={mn:.3f} ms, max={mx:.3f} ms, samples={len(vals)}")

    if overall:
        print("\nOverall latency:")
        print(f"  avg={sum(overall)/len(overall):.3f} ms, min={min(overall):.3f} ms, max={max(overall):.3f} ms, samples={len(overall)}")

    # ----------------------------------------------------
    # APP SIMULATION LOGIC
    # ----------------------------------------------------
    if APPS_CSV.exists():
        app_rows = []
        with APPS_CSV.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                app_rows.append(r)
                
        ms_dict = {ms['service_id']: ms for ms in ms_rows}
        app_out_rows = []
        app_stats = defaultdict(list)
        app_request_id = 0
        
        for app in app_rows:
            app_id = app['app_id']
            chain = app['chain'].split(';')
            slo_val = float(app['latency_max_ms']) if app.get('latency_max_ms') else None
            zone_id = app.get('zone_id', '')
            
            if zone_id == '' or zone_id not in polys:
                continue
                
            poly = polys[zone_id]
            
            for _ in range(args.requests_per_service): # configurable requests per app
                app_request_id += 1
                px, py = sample_point_in_poly(poly, rng)
                
                # find entry node
                entry_node = None
                nearest_dist = float('inf')
                for nid, n in nodes.items():
                    d = euclid((px, py), (n['x'], n['y']))
                    if d < nearest_dist:
                        entry_node = nid
                        nearest_dist = d
                
                if entry_node is None:
                    continue
                    
                current_node = entry_node
                path_latency_total = 0.0
                processing_ms_total = 0.0
                nodes_visited = []
                route_failed = False
                
                # User -> Entry
                path_latency_total += 1.0 * rng.uniform(0.9, 1.1)
                
                for service_id in chain:
                    candidate_node_ids = svc_nodes.get(service_id, [])
                    if not candidate_node_ids:
                        route_failed = True
                        break
                        
                    path_latency, target_node, path = dijkstra(graph, current_node, set(candidate_node_ids), link_usage, congestion_penalty)
                    if target_node is None:
                        route_failed = True
                        break
                        
                    if len(path) > 1:
                        for i in range(len(path) - 1):
                            link_usage[(path[i], path[i+1])] += 1
                        
                    path_latency_total += path_latency * rng.uniform(0.9, 1.1)
                    nodes_visited.append(target_node)
                    
                    # processing
                    ms = ms_dict.get(service_id, {})
                    try:
                        cpu_demand = float(ms.get('cpu_demand') or 0.0)
                    except:
                        cpu_demand = 0.0
                    node = nodes[target_node]
                    try:
                        node_cpu = float(node.get('cpu_capacity_ghz') or 1.0)
                    except:
                        node_cpu = 1.0
                        
                    intensity = str(ms.get('compute_intensity') or '').upper()
                    intensity_factor = 1.0 if intensity.startswith('HIGH') else (0.6 if intensity.startswith('MED') else 0.3)
                    
                    if node_cpu > 0:
                        processing_s = (cpu_demand / node_cpu) * intensity_factor * 1.0
                    else:
                        processing_s = intensity_factor * 1.0
                    processing_ms_total += processing_s * 1000.0
                    
                    current_node = target_node
                    
                if route_failed:
                    continue
                    
                # Return to user
                ret_path_latency, _, ret_path = dijkstra(graph, current_node, {entry_node}, link_usage, congestion_penalty)
                if ret_path_latency == float('inf'):
                    continue # Should not happen but just in case
                
                if len(ret_path) > 1:
                    for i in range(len(ret_path) - 1):
                        link_usage[(ret_path[i], ret_path[i+1])] += 1
                
                path_latency_total += ret_path_latency * rng.uniform(0.9, 1.1)
                path_latency_total += 1.0 * rng.uniform(0.9, 1.1) # Entry -> User
                
                total_ms = path_latency_total + processing_ms_total
                slo_violation = False
                if slo_val is not None and total_ms > slo_val:
                    slo_violation = True
                    
                app_out_rows.append({
                    'request_id': app_request_id,
                    'app_id': app_id,
                    'point_x': f"{px:.6f}", 'point_y': f"{py:.6f}",
                    'entry_node': entry_node,
                    'node_1': nodes_visited[0] if len(nodes_visited)>0 else '',
                    'node_2': nodes_visited[1] if len(nodes_visited)>1 else '',
                    'node_3': nodes_visited[2] if len(nodes_visited)>2 else '',
                    'propagation_ms': f"{path_latency_total:.6f}",
                    'processing_ms': f"{processing_ms_total:.6f}",
                    'total_ms': f"{total_ms:.6f}",
                    'latency_max_ms': f"{slo_val:.6f}" if slo_val else '',
                    'slo_violation': 'YES' if slo_violation else 'NO',
                    'status': 'OK'
                })
                app_stats[app_id].append(total_ms)
                
        # write app CSV
        app_fieldnames = ['request_id','app_id','point_x','point_y','entry_node','node_1','node_2','node_3','propagation_ms','processing_ms','latency_max_ms','slo_violation','total_ms','status']
        with args.apps_out.open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=app_fieldnames)
            writer.writeheader()
            for r in app_out_rows:
                writer.writerow(r)
                
        print("\n--- APP CHAINS SIMULATION SUMMARY ---")
        total_app_reqs = len(app_out_rows)
        if total_app_reqs > 0:
            ok_app_reqs = sum(1 for r in app_out_rows if r['status']=='OK')
            print(f"Total App requests: {total_app_reqs}")
            print(f"Successful: {ok_app_reqs}")
            
            app_violations = sum(1 for r in app_out_rows if r['slo_violation'] == 'YES')
            if app_violations:
                print(f"App SLO violations: {app_violations} ({app_violations/total_app_reqs:.1%})")
            else:
                print("App SLO violations: 0")
                
            print("\nPer-app latency (ms):")
            app_overall = []
            for app, vals in sorted(app_stats.items()):
                if not vals:
                    continue
                avg = sum(vals)/len(vals)
                mn = min(vals)
                mx = max(vals)
                app_overall.extend(vals)
                print(f"  {app}: avg={avg:.3f} ms, min={mn:.3f} ms, max={mx:.3f} ms, samples={len(vals)}")
                
            if app_overall:
                print("\nOverall App latency:")
                print(f"  avg={sum(app_overall)/len(app_overall):.3f} ms, min={min(app_overall):.3f} ms, max={max(app_overall):.3f} ms, samples={len(app_overall)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--requests-per-service', type=int, default=5)
    parser.add_argument('--enforce-slo', action='store_true', help='If set, truncate total latency to latency_max_ms when exceeded')
    parser.add_argument('--response-factor', type=float, default=0.01, help='Fraction of state_size_mb to use as response size when stateful')
    parser.add_argument('--max-response-mb', type=float, default=5.0, help='Maximum response size in MB to assume (cap)')
    parser.add_argument('--placements', type=Path, default=DEFAULT_PLACEMENTS_CSV, help='Path to the placements CSV file')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT_CSV, help='Path to write the simulation results CSV')
    parser.add_argument('--apps-out', type=Path, default=DEFAULT_APPS_OUT_CSV, help='Path to write the app simulation results CSV')
    parser.add_argument('--congestion-penalty', type=float, default=0.0, help='Latency penalty in ms per concurrent use of a link')
    args = parser.parse_args()
    # expose to simulate
    args.requests_per_service = args.__dict__.pop('requests_per_service', 5)
    
    # Ensure outputs directory exists
    args.out.parent.mkdir(parents=True, exist_ok=True)
    
    simulate(args)


if __name__ == '__main__':
    main()
