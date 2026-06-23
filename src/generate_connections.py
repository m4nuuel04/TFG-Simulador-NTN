from pathlib import Path
import csv
import math
import argparse

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
NODES_CSV = DATA_DIR / "nodos_ntn.csv"
CONN_CSV = DATA_DIR / "conexiones_ntn.csv"


def read_nodes(path):
    nodes = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            nodes.append((r["node_id"], float(r["x"]), float(r["y"])))
    return nodes


def euclid(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def generate_edges(nodes, neighbor_dist=2.0, haps_radius=20.0):
    # nodes: list of (id,x,y)
    coords = [(n[1], n[2]) for n in nodes]
    ids = [n[0] for n in nodes]
    # identify HAPS and UAV nodes
    haps = [(nid, x, y) for nid, x, y in nodes if nid.upper().startswith("HAPS") or nid.upper().startswith("HAP")]
    uavs = [(nid, x, y) for nid, x, y in nodes if nid.upper().startswith("UAV")]

    neighbors = {nid: set() for nid in ids}

    # connect each node to all UAVs within neighbor_dist
    for i, nid in enumerate(ids):
        x, y = coords[i]
        for uid, ux, uy in uavs:
            if euclid((x, y), (ux, uy)) <= neighbor_dist + 1e-9:
                neighbors[nid].add(uid)
                neighbors[uid].add(nid)

    # connect UAV-UAV neighbors (symmetric) if within neighbor_dist
    for i, (uid, ux, uy) in enumerate(uavs):
        for j, (vid, vx, vy) in enumerate(uavs):
            if i >= j:
                continue
            if euclid((ux, uy), (vx, vy)) <= neighbor_dist + 1e-9:
                neighbors[uid].add(vid)
                neighbors[vid].add(uid)

    # connect each node to all HAPS that cover it (distance <= haps_radius)
    for i, nid in enumerate(ids):
        x, y = coords[i]
        for hid, hx, hy in haps:
            if euclid((x, y), (hx, hy)) <= haps_radius + 1e-9:
                neighbors[nid].add(hid)
                neighbors[hid].add(nid)

    # build edge set
    edges = set()
    for a, neigh in neighbors.items():
        for b in neigh:
            if a < b:
                edges.add((a, b))
            else:
                edges.add((b, a))
    return sorted(edges)


def main():
    parser = argparse.ArgumentParser(description="Generate conexiones_ntn.csv by UAV neighbor distance and HAPS coverage")
    parser.add_argument("--neighbor-dist", type=float, default=2.0, help="neighbor distance for UAV links, in km")
    parser.add_argument("--haps-radius", type=float, default=20.0, help="HAPS coverage radius in km for HAPS->node links")
    parser.add_argument("--out", type=str, default=str(CONN_CSV), help="output conexiones csv path")
    args = parser.parse_args()

    nodes = read_nodes(NODES_CSV)
    if not nodes:
        raise SystemExit("No nodes found in nodos_ntn.csv")

    edges = generate_edges(nodes, neighbor_dist=args.neighbor_dist, haps_radius=args.haps_radius)

    outp = Path(args.out)
    # backup existing
    if outp.exists():
        bak = outp.with_suffix(outp.suffix + ".bak")
        outp.replace(bak)
        print(f"Backed up existing {outp} -> {bak}")

    with outp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_node_id", "target_node_id"])
        for a, b in edges:
            writer.writerow([a, b])

    print(f"Wrote {len(edges)} edges to {outp}")


if __name__ == "__main__":
    main()
