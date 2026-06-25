from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt

from load_microservices import MicroservicesData
from load_ntn import NTNGraph
from pathlib import Path
import csv


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR.parent / "outputs"
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "placements_random.csv"


@dataclass
class NodeState:
    node_id: str
    node_type: str
    remaining_cpu_ghz: float
    remaining_mem_gib: float
    remaining_bandwidth_mbps: float
    remaining_storage_gb: float
    hosted_services: set[str] = field(default_factory=set)

    def can_host(self, service: dict) -> bool:
        return (
            service["cpu_demand"] <= self.remaining_cpu_ghz
            and service["mem_demand_gib"] <= self.remaining_mem_gib
            and service["bandwidth_mbps"] <= self.remaining_bandwidth_mbps
            and service["storage_gb"] <= self.remaining_storage_gb
        )

    def place(self, service: dict) -> None:
        self.remaining_cpu_ghz -= service["cpu_demand"]
        self.remaining_mem_gib -= service["mem_demand_gib"]
        self.remaining_bandwidth_mbps -= service["bandwidth_mbps"]
        self.remaining_storage_gb -= service["storage_gb"]
        self.hosted_services.add(service["service_id"])


@dataclass
class PlacementRecord:
    app_id: str
    app_name: str
    service_id: str
    service_name: str
    replica_index: int
    node_id: str


@dataclass
class PlacementResult:
    assignments: list[PlacementRecord]
    unplaced_replicas: list[tuple[str, int]]
    requested_replicas: int
    placed_replicas: int


def parse_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def normalize_service(row: dict, node_count: int) -> dict:
    scalability_factor = parse_float(row.get("scalability_factor"), 0.0)
    requested_replicas = max(1, math.ceil(scalability_factor * node_count))
    bandwidth_mbps = parse_float(row.get("bandwidth_mbps"), parse_float(row.get("throughput_min_kbps"), 0.0) / 1000.0)
    storage_gb = parse_float(row.get("state_size_mb"), 0.0) / 1024.0

    return {
        "app_id": row.get("app_id", ""),
        "app_name": row.get("app_name", ""),
        "service_id": row.get("service_id", ""),
        "service_name": row.get("service_name", ""),
        "cpu_demand": parse_float(row.get("cpu_demand"), 0.0),
        "mem_demand_gib": parse_float(row.get("mem_demand_gib"), 0.0),
        "bandwidth_mbps": bandwidth_mbps,
        "storage_gb": storage_gb,
        "requested_replicas": requested_replicas,
        # zoning attributes (may be empty)
        "zone_id": row.get("zone_id", ""),
        "callable_from_circuit": str(row.get("callable_from_circuit", "NO")).upper(),
    }


def build_node_states(graph: NTNGraph) -> list[NodeState]:
    ordered_nodes = sorted(graph.nodes.values(), key=lambda node: node.node_id)
    return [
        NodeState(
            node_id=node.node_id,
            node_type=node.node_type,
            remaining_cpu_ghz=node.cpu_capacity_ghz,
            remaining_mem_gib=node.mem_capacity_gib,
            remaining_bandwidth_mbps=node.bandwidth_capacity_mbps,
            remaining_storage_gb=node.storage_capacity_gb,
        )
        for node in ordered_nodes
    ]


def place_microservices_randomly(graph: NTNGraph, services: list[dict], seed: int | None = None) -> PlacementResult:
    rng = random.Random(seed)
    node_states = build_node_states(graph)
    node_count = len(node_states)

    assignments: list[PlacementRecord] = []
    unplaced_replicas: list[tuple[str, int]] = []
    requested_replicas = 0

    # Prepare mutable service list with placement counters
    svc_list = []
    for service in services:
        svc = dict(service)
        svc['placed'] = 0
        svc_list.append(svc)
        requested_replicas += svc['requested_replicas']

    # Phase 1: ensure every node has at least one microservice (if possible)
    node_order = list(range(node_count))
    rng.shuffle(node_order)
    for idx in node_order:
        node_state = node_states[idx]
        candidates = [s for s in svc_list if s['placed'] < s['requested_replicas'] and s['service_id'] not in node_state.hosted_services and node_state.can_host(s)]
        if not candidates:
            continue
        svc = rng.choice(candidates)
        node_state.place(svc)
        svc['placed'] += 1
        assignments.append(
            PlacementRecord(
                app_id=svc['app_id'],
                app_name=svc['app_name'],
                service_id=svc['service_id'],
                service_name=svc['service_name'],
                replica_index=svc['placed'],
                node_id=node_state.node_id,
            )
        )

    # Phase 2: place remaining replicas randomly across all nodes
    for svc in svc_list:
        while svc['placed'] < svc['requested_replicas']:
            replica_index = svc['placed'] + 1
            start_index = rng.randrange(node_count)
            placed = False
            for offset in range(node_count):
                node_state = node_states[(start_index + offset) % node_count]
                if svc['service_id'] in node_state.hosted_services:
                    continue
                if not node_state.can_host(svc):
                    continue

                node_state.place(svc)
                svc['placed'] += 1
                assignments.append(
                    PlacementRecord(
                        app_id=svc['app_id'],
                        app_name=svc['app_name'],
                        service_id=svc['service_id'],
                        service_name=svc['service_name'],
                        replica_index=replica_index,
                        node_id=node_state.node_id,
                    )
                )
                placed = True
                break

            if not placed:
                unplaced_replicas.append((svc['service_id'], replica_index))
                break

    return PlacementResult(
        assignments=assignments,
        unplaced_replicas=unplaced_replicas,
        requested_replicas=requested_replicas,
        placed_replicas=len(assignments),
    )


def save_assignments_csv(assignments: list[PlacementRecord], output_path: Path) -> None:
    fieldnames = ["app_id", "app_name", "service_id", "service_name", "replica_index", "node_id"]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in assignments:
            writer.writerow(
                {
                    "app_id": record.app_id,
                    "app_name": record.app_name,
                    "service_id": record.service_id,
                    "service_name": record.service_name,
                    "replica_index": record.replica_index,
                    "node_id": record.node_id,
                }
            )


def print_service_summary(result: PlacementResult, services: list[dict]) -> None:
    assignments_by_service: dict[str, list[PlacementRecord]] = defaultdict(list)

    for record in result.assignments:
        assignments_by_service[record.service_id].append(record)

    print()
    print("RESUMEN POR MICROSERVICIO")
    print("=" * 60)

    for service in services:
        service_id = service["service_id"]
        records = assignments_by_service.get(service_id, [])
        node_list = ", ".join(record.node_id for record in records) if records else "Sin colocacion"
        unplaced_count = service["requested_replicas"] - len(records)

        print(f"{service_id} - {service['service_name']}")
        print(f"  Solicitadas: {service['requested_replicas']}")
        print(f"  Colocadas:   {len(records)}")
        print(f"  No colocadas: {unplaced_count}")
        print(f"  Nodos:       {node_list}")


def build_node_assignments(result: PlacementResult) -> dict[str, list[PlacementRecord]]:
    assignments_by_node: dict[str, list[PlacementRecord]] = defaultdict(list)
    for record in result.assignments:
        assignments_by_node[record.node_id].append(record)
    return assignments_by_node


def save_node_report_markdown(assignments_by_node: dict[str, list[PlacementRecord]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# Colocacion por nodo NTN\n\n")
        fh.write("Este informe muestra cuantos microservicios hay en cada nodo y cuales son.\n\n")

        for node_id in sorted(assignments_by_node):
            records = assignments_by_node[node_id]
            fh.write(f"## {node_id}\n\n")
            fh.write(f"Microservicios colocados: {len(records)}\n\n")
            for record in records:
                fh.write(f"- {record.service_id} - {record.service_name} (replica {record.replica_index})\n")
            fh.write("\n")


def save_placement_plot(graph: NTNGraph, result: PlacementResult, output_path: Path) -> None:
    assignments_by_node = build_node_assignments(result)
    node_counts = {node.node_id: len(assignments_by_node.get(node.node_id, [])) for node in graph.nodes.values()}
    ordered_nodes = sorted(graph.nodes.values(), key=lambda node: (-node_counts[node.node_id], node.node_id))
    top_nodes = [node for node in ordered_nodes if node_counts[node.node_id] > 0][:120]

    labels = [node.node_id for node in top_nodes]
    values = [node_counts[node.node_id] for node in top_nodes]
    bar_colors = [plt.cm.viridis(min(1.0, value / max(values))) for value in values]

    fig, ax = plt.subplots(figsize=(18, 10), dpi=130)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f8fafc")

    ax.bar(range(len(top_nodes)), values, color=bar_colors, width=0.82, edgecolor="#334155", linewidth=0.4)
    ax.set_title("Microservicios por nodo NTN", fontsize=36)
    ax.set_xlabel("Nodo", fontsize=32)
    ax.set_ylabel("Numero de microservicios", fontsize=32)
    ax.set_xticks(range(len(top_nodes)))
    ax.set_xticklabels(labels, rotation=90, fontsize=16)
    ax.grid(axis="y", linestyle="--", alpha=0.25)

    for index, value in enumerate(values):
        ax.text(index, value + 0.05, str(value), ha="center", va="bottom", fontsize=14)

    if len(top_nodes) < len(graph.nodes):
        ax.text(
            0.99,
            0.98,
            f"Mostrando {len(top_nodes)} nodos con carga; informe completo en el Markdown",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="#cbd5e1"),
        )

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor='white', transparent=False)
    plt.close(fig)


def main() -> None:
    # Ensure outputs directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Random placement of microservices onto NTN nodes.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible placements")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_CSV, help="CSV file to write the placement result")
    parser.add_argument("--plot-out", type=Path, default=OUTPUT_DIR / "placements_random.png", help="PNG file to write the placement visualization")
    parser.add_argument("--node-report-out", type=Path, default=OUTPUT_DIR / "placements_by_node.md", help="Markdown file with the microservices grouped by node")
    args = parser.parse_args()

    graph = NTNGraph.from_csvs()
    # Prefer zonified microservices if present
    zonified = Path("data") / "microservicios_zonificados.csv"
    if zonified.exists():
        ms_data = MicroservicesData(csv_path=zonified)
    else:
        ms_data = MicroservicesData()

    services = [normalize_service(row, len(graph.nodes)) for row in ms_data.get_all_data().to_dict("records")]

    result = place_microservices_randomly(graph, services, seed=args.seed)
    save_assignments_csv(result.assignments, args.out)
    save_placement_plot(graph, result, args.plot_out)
    save_node_report_markdown(build_node_assignments(result), args.node_report_out)

    print("RESUMEN DE COLOCACION ALEATORIA")
    print(f"Nodos disponibles: {len(graph.nodes)}")
    print(f"Replicas solicitadas: {result.requested_replicas}")
    print(f"Replicas colocadas: {result.placed_replicas}")
    print(f"Replicas no colocadas: {len(result.unplaced_replicas)}")
    print(f"Salida escrita en: {args.out}")
    print(f"Visualizacion escrita en: {args.plot_out}")
    print(f"Informe por nodo escrito en: {args.node_report_out}")

    print_service_summary(result, services)


if __name__ == "__main__":
    main()