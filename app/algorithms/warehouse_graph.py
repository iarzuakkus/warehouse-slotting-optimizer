"""Düzenli depo ızgarası ve ağırlıklı en kısa yol hesapları."""

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import inf, isfinite


DISPATCH_NODE = "dispatch"


@dataclass(frozen=True, order=True)
class LocationKey:
    """Bir fiziksel raf lokasyonunun hiyerarşik anahtarı."""

    aisle: int
    bay: int
    level: int
    slot: int


@dataclass(frozen=True)
class ShortestPath:
    """İki düğüm arasındaki toplam mesafe ve izlenen düğümler."""

    distance_m: float
    nodes: tuple[str, ...]


@dataclass(frozen=True, order=True)
class GraphEdge:
    """Görselleştirmede kullanılacak benzersiz ve ağırlıklı graf kenarı."""

    source: str
    target: str
    distance_m: float


@dataclass(frozen=True)
class WarehouseGraphConfig:
    """Sentetik depo ızgarasının boyutları ve fiziksel mesafeleri."""

    aisle_count: int
    bays_per_aisle: int
    levels_per_bay: int
    slots_per_level: int
    aisle_spacing_m: float = 20.0
    bay_spacing_m: float = 3.0
    level_access_m: float = 1.0
    slot_access_m: float = 0.25

    def __post_init__(self) -> None:
        counts = (
            self.aisle_count,
            self.bays_per_aisle,
            self.levels_per_bay,
            self.slots_per_level,
        )
        if any(value <= 0 for value in counts):
            raise ValueError("Warehouse dimensions must be positive")

        distances = (
            self.aisle_spacing_m,
            self.bay_spacing_m,
            self.level_access_m,
            self.slot_access_m,
        )
        if any(not isfinite(value) or value <= 0 for value in distances):
            raise ValueError("Warehouse distances must be positive and finite")


@dataclass
class WarehouseGraph:
    """Çift yönlü ağırlıklı depo grafı."""

    _adjacency: dict[str, dict[str, float]] = field(default_factory=dict)
    _location_nodes: dict[LocationKey, str] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self._adjacency)

    @property
    def location_count(self) -> int:
        return len(self._location_nodes)

    def nodes(self) -> tuple[str, ...]:
        """Graf düğümlerini kararlı alfabetik sırayla döndürür."""
        return tuple(sorted(self._adjacency))

    def edges(self) -> tuple[GraphEdge, ...]:
        """Çift yönlü graf kenarlarını tekrarsız ve kararlı sırayla döndürür."""
        edges: list[GraphEdge] = []
        for source in sorted(self._adjacency):
            for target, distance_m in sorted(
                self._adjacency[source].items()
            ):
                if source < target:
                    edges.append(
                        GraphEdge(
                            source=source,
                            target=target,
                            distance_m=distance_m,
                        )
                    )
        return tuple(edges)

    def add_node(self, node: str) -> None:
        if not node:
            raise ValueError("Node name cannot be empty")
        self._adjacency.setdefault(node, {})

    def connect(self, first: str, second: str, distance_m: float) -> None:
        """İki düğümü pozitif mesafeli, çift yönlü bir kenarla bağlar."""
        if first == second:
            raise ValueError("An edge must connect two different nodes")
        if not isfinite(distance_m) or distance_m <= 0:
            raise ValueError("Edge distance must be positive and finite")

        self.add_node(first)
        self.add_node(second)
        current_distance = self._adjacency[first].get(second, inf)
        effective_distance = min(current_distance, float(distance_m))
        self._adjacency[first][second] = effective_distance
        self._adjacency[second][first] = effective_distance

    def register_location(self, key: LocationKey, node: str) -> None:
        if key in self._location_nodes:
            raise ValueError(f"Location is already registered: {key}")
        self.add_node(node)
        self._location_nodes[key] = node

    def location_node(self, key: LocationKey) -> str:
        try:
            return self._location_nodes[key]
        except KeyError as exc:
            raise ValueError(f"Unknown warehouse location: {key}") from exc

    def shortest_path(self, start: str, destination: str) -> ShortestPath:
        """Dijkstra algoritmasıyla iki düğüm arasındaki en kısa yolu döndürür."""
        if start not in self._adjacency:
            raise ValueError(f"Unknown start node: {start}")
        if destination not in self._adjacency:
            raise ValueError(f"Unknown destination node: {destination}")

        distances = {start: 0.0}
        previous: dict[str, str] = {}
        queue: list[tuple[float, str]] = [(0.0, start)]

        while queue:
            current_distance, current = heappop(queue)
            if current_distance > distances[current]:
                continue
            if current == destination:
                break

            for neighbor, edge_distance in self._adjacency[current].items():
                candidate = current_distance + edge_distance
                if candidate < distances.get(neighbor, inf):
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heappush(queue, (candidate, neighbor))

        if destination not in distances:
            raise ValueError(f"No path between {start} and {destination}")

        nodes = [destination]
        while nodes[-1] != start:
            nodes.append(previous[nodes[-1]])
        nodes.reverse()
        return ShortestPath(distance_m=distances[destination], nodes=tuple(nodes))

    def shortest_path_to_location(self, key: LocationKey) -> ShortestPath:
        return self.shortest_path(DISPATCH_NODE, self.location_node(key))


def _pickup_node(aisle: int, bay: int) -> str:
    return f"pickup:A{aisle:03d}:B{bay:03d}"


def _location_node(key: LocationKey) -> str:
    return (
        f"location:A{key.aisle:03d}:B{key.bay:03d}:"
        f"L{key.level:02d}:S{key.slot:02d}"
    )


def build_regular_warehouse_graph(
    config: WarehouseGraphConfig,
) -> WarehouseGraph:
    """Ön ve arka çapraz geçişli düzenli bir depo grafı üretir."""
    graph = WarehouseGraph()
    graph.add_node(DISPATCH_NODE)

    for aisle in range(1, config.aisle_count + 1):
        for bay in range(1, config.bays_per_aisle + 1):
            pickup_node = _pickup_node(aisle, bay)
            graph.add_node(pickup_node)

            if bay > 1:
                graph.connect(
                    _pickup_node(aisle, bay - 1),
                    pickup_node,
                    config.bay_spacing_m,
                )

            for level in range(1, config.levels_per_bay + 1):
                for slot in range(1, config.slots_per_level + 1):
                    key = LocationKey(aisle, bay, level, slot)
                    location_node = _location_node(key)
                    graph.register_location(key, location_node)
                    graph.connect(
                        pickup_node,
                        location_node,
                        level * config.level_access_m
                        + slot * config.slot_access_m,
                    )

    first_pickup = _pickup_node(1, 1)
    graph.connect(
        DISPATCH_NODE,
        first_pickup,
        config.aisle_spacing_m + config.bay_spacing_m,
    )

    for aisle in range(2, config.aisle_count + 1):
        previous_aisle = aisle - 1
        graph.connect(
            _pickup_node(previous_aisle, 1),
            _pickup_node(aisle, 1),
            config.aisle_spacing_m,
        )
        graph.connect(
            _pickup_node(previous_aisle, config.bays_per_aisle),
            _pickup_node(aisle, config.bays_per_aisle),
            config.aisle_spacing_m,
        )

    return graph
