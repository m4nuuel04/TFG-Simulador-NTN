from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
NODES_CSV = DATA_DIR / "nodos_ntn.csv"
CONNECTIONS_CSV = DATA_DIR / "conexiones_ntn.csv"


@dataclass
class NTNNode:
    node_id: str
    node_type: str
    x: float
    y: float
    cpu_capacity_ghz: float = 0.0
    mem_capacity_gib: float = 0.0
    bandwidth_capacity_mbps: float = 0.0
    storage_capacity_gb: float = 0.0
    neighbors: set[str] = field(default_factory=set)

    def connect(self, other_node_id: str) -> None:
        self.neighbors.add(other_node_id)

    def can_host(
        self,
        cpu_demand: float,
        mem_demand_gib: float,
        bandwidth_mbps: float,
        storage_gb: float = 0.0,
    ) -> bool:
        return (
            self.cpu_capacity_ghz >= cpu_demand
            and self.mem_capacity_gib >= mem_demand_gib
            and self.bandwidth_capacity_mbps >= bandwidth_mbps
            and self.storage_capacity_gb >= storage_gb
        )


class NTNGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, NTNNode] = {}

    def add_node(self, node: NTNNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"El nodo '{node.node_id}' ya existe en el grafo")
        self.nodes[node.node_id] = node

    def add_connection(self, source_node_id: str, target_node_id: str) -> None:
        if source_node_id not in self.nodes:
            raise ValueError(f"El nodo origen '{source_node_id}' no existe")
        if target_node_id not in self.nodes:
            raise ValueError(f"El nodo destino '{target_node_id}' no existe")

        self.nodes[source_node_id].connect(target_node_id)
        self.nodes[target_node_id].connect(source_node_id)

    @classmethod
    def from_csvs(cls, nodes_csv: Path = NODES_CSV, connections_csv: Path = CONNECTIONS_CSV) -> "NTNGraph":
        graph = cls()

        with nodes_csv.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                graph.add_node(
                    NTNNode(
                        node_id=row["node_id"],
                        node_type=row["node_type"],
                        x=float(row["x"]),
                        y=float(row["y"]),
                        cpu_capacity_ghz=float(row.get("cpu_capacity_ghz", 0) or 0),
                        mem_capacity_gib=float(row.get("mem_capacity_gib", 0) or 0),
                        bandwidth_capacity_mbps=float(row.get("bandwidth_capacity_mbps", 0) or 0),
                        storage_capacity_gb=float(row.get("storage_capacity_gb", 0) or 0),
                    )
                )

        with connections_csv.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                graph.add_connection(row["source_node_id"], row["target_node_id"])

        return graph

    def get_neighbors(self, node_id: str) -> list[str]:
        if node_id not in self.nodes:
            raise ValueError(f"El nodo '{node_id}' no existe en el grafo")
        return sorted(self.nodes[node_id].neighbors)

    def print_summary(self) -> None:
        print("=" * 60)
        print("RESUMEN DEL GRAFO NTN")
        print("=" * 60)
        print(f"Nodos: {len(self.nodes)}")

        edge_count = sum(len(node.neighbors) for node in self.nodes.values()) // 2
        print(f"Conexiones bidireccionales: {edge_count}")

        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            neighbors = ", ".join(sorted(node.neighbors)) if node.neighbors else "Sin conexiones"
            print(f"{node.node_id} ({node.node_type}): {neighbors}")


if __name__ == "__main__":
    graph = NTNGraph.from_csvs()
    graph.print_summary()