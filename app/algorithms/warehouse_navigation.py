"""Obstacle-aware deterministic navigation for warehouse equipment."""

from dataclasses import dataclass, field
from decimal import Decimal
from heapq import heappop, heappush
from math import inf
from types import MappingProxyType
from typing import Literal, Mapping
import re


EquipmentType = Literal["cart", "pallet_jack", "forklift"]
NodeType = Literal[
    "dispatch",
    "staging",
    "cross_aisle",
    "aisle",
    "approach",
]

ZERO = Decimal("0")
TWO = Decimal("2")


class WarehouseNavigationError(ValueError):
    """Base error for invalid or unreachable physical navigation."""


class WarehouseNavigationConfigurationError(WarehouseNavigationError):
    """Raised when rack geometry cannot form safe driving corridors."""


class WarehouseNavigationRouteError(WarehouseNavigationError):
    """Raised when a requested safe route cannot be found."""


@dataclass(frozen=True)
class EquipmentNavigationProfile:
    equipment_type: EquipmentType
    width_m: Decimal
    safety_clearance_m: Decimal

    def __post_init__(self) -> None:
        if self.width_m <= 0 or self.safety_clearance_m <= 0:
            raise ValueError(
                "Equipment width and safety clearance must be positive"
            )

    @property
    def obstacle_margin_m(self) -> Decimal:
        """Clearance required by the vehicle center around an obstacle."""
        return self.width_m / TWO + self.safety_clearance_m


EQUIPMENT_NAVIGATION_PROFILES: Mapping[
    EquipmentType,
    EquipmentNavigationProfile,
] = MappingProxyType(
    {
        "cart": EquipmentNavigationProfile(
            equipment_type="cart",
            width_m=Decimal("0.65"),
            safety_clearance_m=Decimal("0.35"),
        ),
        "pallet_jack": EquipmentNavigationProfile(
            equipment_type="pallet_jack",
            width_m=Decimal("0.80"),
            safety_clearance_m=Decimal("0.55"),
        ),
        "forklift": EquipmentNavigationProfile(
            equipment_type="forklift",
            width_m=Decimal("1.20"),
            safety_clearance_m=Decimal("0.85"),
        ),
    }
)


@dataclass(frozen=True)
class PhysicalRack:
    aisle: str
    bay: str
    width_m: Decimal
    depth_m: Decimal

    def __post_init__(self) -> None:
        if not self.aisle or not self.bay:
            raise ValueError("Rack aisle and bay cannot be empty")
        if self.width_m <= 0 or self.depth_m <= 0:
            raise ValueError("Rack width and depth must be positive")

    @property
    def key(self) -> tuple[str, str]:
        return self.aisle, self.bay


@dataclass(frozen=True)
class WarehouseNavigationConfig:
    """Derived layout rules until rack ground coordinates are persisted."""

    drive_aisle_width_m: Decimal = Decimal("3.50")
    cross_aisle_width_m: Decimal = Decimal("4.00")
    rack_gap_m: Decimal = Decimal("0.20")
    boundary_padding_m: Decimal = Decimal("1.00")
    approach_epsilon_m: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        values = (
            self.drive_aisle_width_m,
            self.cross_aisle_width_m,
            self.rack_gap_m,
            self.boundary_padding_m,
            self.approach_epsilon_m,
        )
        if any(value <= 0 for value in values):
            raise ValueError("Navigation layout distances must be positive")


@dataclass(frozen=True)
class AxisAlignedBounds:
    min_x_m: Decimal
    min_y_m: Decimal
    max_x_m: Decimal
    max_y_m: Decimal

    def __post_init__(self) -> None:
        if self.max_x_m <= self.min_x_m or self.max_y_m <= self.min_y_m:
            raise ValueError("AABB maximums must exceed minimums")

    def expanded(self, margin_m: Decimal) -> "AxisAlignedBounds":
        if margin_m < 0:
            raise ValueError("AABB expansion margin cannot be negative")
        return AxisAlignedBounds(
            min_x_m=self.min_x_m - margin_m,
            min_y_m=self.min_y_m - margin_m,
            max_x_m=self.max_x_m + margin_m,
            max_y_m=self.max_y_m + margin_m,
        )

    def contains(
        self,
        x_m: Decimal,
        y_m: Decimal,
        *,
        inclusive: bool = True,
    ) -> bool:
        if inclusive:
            return (
                self.min_x_m <= x_m <= self.max_x_m
                and self.min_y_m <= y_m <= self.max_y_m
            )
        return (
            self.min_x_m < x_m < self.max_x_m
            and self.min_y_m < y_m < self.max_y_m
        )


@dataclass(frozen=True)
class RackObstacle:
    aisle: str
    bay: str
    physical_bounds: AxisAlignedBounds
    blocked_bounds: AxisAlignedBounds

    @property
    def key(self) -> tuple[str, str]:
        return self.aisle, self.bay


@dataclass(frozen=True)
class NavigationNode:
    id: str
    type: NodeType
    x_m: Decimal
    y_m: Decimal


@dataclass(frozen=True)
class NavigationRoute:
    distance_m: Decimal
    nodes: tuple[NavigationNode, ...]


@dataclass
class WarehouseNavigationSnapshot:
    equipment_profile: EquipmentNavigationProfile
    warehouse_bounds: AxisAlignedBounds
    obstacles: tuple[RackObstacle, ...]
    nodes_by_id: dict[str, NavigationNode]
    approach_node_ids_by_rack: dict[tuple[str, str], str]
    _adjacency: dict[str, dict[str, Decimal]] = field(repr=False)

    def path_from_dispatch(self, aisle: str, bay: str) -> NavigationRoute:
        return self.shortest_path(
            "dispatch",
            self._approach_node_id(aisle, bay),
        )

    def path_between_racks(
        self,
        start_aisle: str,
        start_bay: str,
        destination_aisle: str,
        destination_bay: str,
    ) -> NavigationRoute:
        return self.shortest_path(
            self._approach_node_id(start_aisle, start_bay),
            self._approach_node_id(destination_aisle, destination_bay),
        )

    def path_to_dispatch(self, aisle: str, bay: str) -> NavigationRoute:
        return self.shortest_path(
            self._approach_node_id(aisle, bay),
            "dispatch",
        )

    def path_from_staging(self, aisle: str, bay: str) -> NavigationRoute:
        return self.shortest_path(
            "staging",
            self._approach_node_id(aisle, bay),
        )

    def path_to_staging(self, aisle: str, bay: str) -> NavigationRoute:
        return self.shortest_path(
            self._approach_node_id(aisle, bay),
            "staging",
        )

    def shortest_path(
        self,
        start_node_id: str,
        destination_node_id: str,
    ) -> NavigationRoute:
        if start_node_id not in self.nodes_by_id:
            raise WarehouseNavigationRouteError(
                f"Unknown navigation start node: {start_node_id}"
            )
        if destination_node_id not in self.nodes_by_id:
            raise WarehouseNavigationRouteError(
                f"Unknown navigation destination node: "
                f"{destination_node_id}"
            )

        distances = {start_node_id: ZERO}
        previous: dict[str, str] = {}
        queue: list[tuple[Decimal, str]] = [(ZERO, start_node_id)]
        while queue:
            current_distance, current = heappop(queue)
            if current_distance > distances[current]:
                continue
            if current == destination_node_id:
                break
            for neighbor, edge_distance in sorted(
                self._adjacency[current].items()
            ):
                candidate = current_distance + edge_distance
                if candidate < distances.get(neighbor, Decimal(str(inf))):
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heappush(queue, (candidate, neighbor))

        if destination_node_id not in distances:
            raise WarehouseNavigationRouteError(
                f"No safe navigation route from {start_node_id} to "
                f"{destination_node_id}"
            )

        node_ids = [destination_node_id]
        while node_ids[-1] != start_node_id:
            node_ids.append(previous[node_ids[-1]])
        node_ids.reverse()
        route = NavigationRoute(
            distance_m=distances[destination_node_id],
            nodes=tuple(self.nodes_by_id[node_id] for node_id in node_ids),
        )
        self.validate_route(route)
        return route

    def validate_route(self, route: NavigationRoute) -> None:
        if not route.nodes:
            raise WarehouseNavigationRouteError(
                "Navigation route cannot be empty"
            )
        for node in route.nodes:
            if not self.warehouse_bounds.contains(node.x_m, node.y_m):
                raise WarehouseNavigationRouteError(
                    f"Navigation node {node.id} is outside warehouse bounds"
                )
        for start, end in zip(route.nodes, route.nodes[1:]):
            if not self.segment_is_safe(start, end):
                raise WarehouseNavigationRouteError(
                    f"Navigation segment {start.id} -> {end.id} "
                    "intersects a rack obstacle"
                )

    def segment_is_safe(
        self,
        start: NavigationNode,
        end: NavigationNode,
    ) -> bool:
        return all(
            not segment_intersects_aabb(
                start.x_m,
                start.y_m,
                end.x_m,
                end.y_m,
                obstacle.blocked_bounds,
            )
            for obstacle in self.obstacles
        )

    def edge_distance(
        self,
        first_node_id: str,
        second_node_id: str,
    ) -> Decimal:
        try:
            return self._adjacency[first_node_id][second_node_id]
        except KeyError as exc:
            raise WarehouseNavigationRouteError(
                f"Navigation nodes are not adjacent: "
                f"{first_node_id}, {second_node_id}"
            ) from exc

    def _approach_node_id(self, aisle: str, bay: str) -> str:
        try:
            return self.approach_node_ids_by_rack[(aisle, bay)]
        except KeyError as exc:
            raise WarehouseNavigationRouteError(
                f"Rack {aisle}/{bay} has no safe approach point"
            ) from exc


def build_warehouse_navigation(
    racks: list[PhysicalRack],
    equipment_type: EquipmentType,
    config: WarehouseNavigationConfig | None = None,
) -> WarehouseNavigationSnapshot:
    """Build a safe graph around vertically oriented rack obstacles."""
    if not racks:
        raise WarehouseNavigationConfigurationError(
            "At least one physical rack is required"
        )
    try:
        profile = EQUIPMENT_NAVIGATION_PROFILES[equipment_type]
    except KeyError as exc:
        raise WarehouseNavigationConfigurationError(
            f"Unsupported equipment type: {equipment_type}"
        ) from exc
    effective_config = config or WarehouseNavigationConfig()
    margin = profile.obstacle_margin_m
    minimum_aisle_width = (
        margin * TWO + effective_config.approach_epsilon_m * TWO
    )
    if effective_config.drive_aisle_width_m <= minimum_aisle_width:
        raise WarehouseNavigationConfigurationError(
            f"Drive aisle width {effective_config.drive_aisle_width_m} m "
            f"is insufficient for {equipment_type}; it must exceed "
            f"{minimum_aisle_width} m"
        )
    if (
        effective_config.cross_aisle_width_m / TWO
        <= margin + effective_config.approach_epsilon_m
    ):
        raise WarehouseNavigationConfigurationError(
            f"Cross aisle width is insufficient for {equipment_type}"
        )

    unique_racks: dict[tuple[str, str], PhysicalRack] = {}
    for rack in racks:
        if rack.key in unique_racks:
            raise WarehouseNavigationConfigurationError(
                f"Duplicate physical rack: {rack.aisle}/{rack.bay}"
            )
        unique_racks[rack.key] = rack

    aisle_names = sorted(
        {rack.aisle for rack in racks},
        key=_natural_code_key,
    )
    bay_names = sorted(
        {rack.bay for rack in racks},
        key=_natural_code_key,
    )
    aisle_depths = {
        aisle: max(
            rack.depth_m for rack in racks if rack.aisle == aisle
        )
        for aisle in aisle_names
    }
    bay_widths = {
        bay: max(rack.width_m for rack in racks if rack.bay == bay)
        for bay in bay_names
    }

    aisle_min_x: dict[str, Decimal] = {}
    next_x = effective_config.drive_aisle_width_m
    for aisle in aisle_names:
        aisle_min_x[aisle] = next_x
        next_x += (
            aisle_depths[aisle]
            + effective_config.drive_aisle_width_m
        )

    bay_min_y: dict[str, Decimal] = {}
    next_y = effective_config.cross_aisle_width_m
    for bay in bay_names:
        bay_min_y[bay] = next_y
        next_y += bay_widths[bay] + effective_config.rack_gap_m
    rack_area_max_y = (
        bay_min_y[bay_names[-1]] + bay_widths[bay_names[-1]]
    )

    obstacles: list[RackObstacle] = []
    for rack in sorted(
        racks,
        key=lambda item: (
            _natural_code_key(item.aisle),
            _natural_code_key(item.bay),
        ),
    ):
        row_offset = (bay_widths[rack.bay] - rack.width_m) / TWO
        physical = AxisAlignedBounds(
            min_x_m=aisle_min_x[rack.aisle],
            min_y_m=bay_min_y[rack.bay] + row_offset,
            max_x_m=aisle_min_x[rack.aisle] + rack.depth_m,
            max_y_m=bay_min_y[rack.bay] + row_offset + rack.width_m,
        )
        obstacles.append(
            RackObstacle(
                aisle=rack.aisle,
                bay=rack.bay,
                physical_bounds=physical,
                blocked_bounds=physical.expanded(margin),
            )
        )

    warehouse_bounds = AxisAlignedBounds(
        min_x_m=ZERO,
        min_y_m=ZERO,
        max_x_m=(
            aisle_min_x[aisle_names[-1]]
            + aisle_depths[aisle_names[-1]]
            + effective_config.boundary_padding_m
        ),
        max_y_m=(
            rack_area_max_y
            + effective_config.cross_aisle_width_m
        ),
    )
    nodes: dict[str, NavigationNode] = {}
    adjacency: dict[str, dict[str, Decimal]] = {}
    approach_by_rack: dict[tuple[str, str], str] = {}

    def add_node(node: NavigationNode) -> None:
        if node.id in nodes:
            raise WarehouseNavigationConfigurationError(
                f"Duplicate navigation node: {node.id}"
            )
        if not warehouse_bounds.contains(node.x_m, node.y_m):
            raise WarehouseNavigationConfigurationError(
                f"Navigation node {node.id} is outside warehouse bounds"
            )
        nodes[node.id] = node
        adjacency[node.id] = {}

    south_cross_y = effective_config.cross_aisle_width_m / TWO
    north_cross_y = (
        rack_area_max_y + effective_config.cross_aisle_width_m / TWO
    )
    dispatch = NavigationNode(
        id="dispatch",
        type="dispatch",
        x_m=ZERO,
        y_m=south_cross_y,
    )
    staging = NavigationNode(
        id="staging",
        type="staging",
        x_m=ZERO,
        y_m=north_cross_y,
    )
    add_node(dispatch)
    add_node(staging)

    aisle_chain_node_ids: dict[str, list[str]] = {}
    for aisle_index, aisle in enumerate(aisle_names):
        if aisle_index == 0:
            aisle_center_x = (
                aisle_min_x[aisle]
                - effective_config.drive_aisle_width_m / TWO
            )
        else:
            previous_aisle = aisle_names[aisle_index - 1]
            previous_right = (
                aisle_min_x[previous_aisle]
                + aisle_depths[previous_aisle]
            )
            aisle_center_x = (
                previous_right + aisle_min_x[aisle]
            ) / TWO

        south_id = f"cross_aisle:south:{aisle}"
        north_id = f"cross_aisle:north:{aisle}"
        add_node(
            NavigationNode(
                id=south_id,
                type="cross_aisle",
                x_m=aisle_center_x,
                y_m=south_cross_y,
            )
        )
        chain = [south_id]
        for rack in sorted(
            (item for item in racks if item.aisle == aisle),
            key=lambda item: _natural_code_key(item.bay),
        ):
            obstacle = next(
                item for item in obstacles if item.key == rack.key
            )
            approach_y = (
                obstacle.physical_bounds.min_y_m
                + obstacle.physical_bounds.max_y_m
            ) / TWO
            aisle_node_id = f"aisle:{aisle}:{rack.bay}"
            approach_node_id = f"approach:{aisle}:{rack.bay}:left"
            add_node(
                NavigationNode(
                    id=aisle_node_id,
                    type="aisle",
                    x_m=aisle_center_x,
                    y_m=approach_y,
                )
            )
            add_node(
                NavigationNode(
                    id=approach_node_id,
                    type="approach",
                    x_m=(
                        obstacle.blocked_bounds.min_x_m
                        - effective_config.approach_epsilon_m
                    ),
                    y_m=approach_y,
                )
            )
            approach_by_rack[rack.key] = approach_node_id
            chain.append(aisle_node_id)
        chain.append(north_id)
        add_node(
            NavigationNode(
                id=north_id,
                type="cross_aisle",
                x_m=aisle_center_x,
                y_m=north_cross_y,
            )
        )
        aisle_chain_node_ids[aisle] = chain

    snapshot = WarehouseNavigationSnapshot(
        equipment_profile=profile,
        warehouse_bounds=warehouse_bounds,
        obstacles=tuple(obstacles),
        nodes_by_id=nodes,
        approach_node_ids_by_rack=approach_by_rack,
        _adjacency=adjacency,
    )

    def connect(first_id: str, second_id: str) -> None:
        first = nodes[first_id]
        second = nodes[second_id]
        if not snapshot.segment_is_safe(first, second):
            return
        distance = _segment_length_m(first, second)
        if distance <= 0:
            raise WarehouseNavigationConfigurationError(
                f"Navigation edge has no length: {first_id}, {second_id}"
            )
        adjacency[first_id][second_id] = distance
        adjacency[second_id][first_id] = distance

    for aisle, chain in aisle_chain_node_ids.items():
        for first_id, second_id in zip(chain, chain[1:]):
            connect(first_id, second_id)
        for rack in (item for item in racks if item.aisle == aisle):
            connect(
                f"aisle:{aisle}:{rack.bay}",
                approach_by_rack[rack.key],
            )

    for first_aisle, second_aisle in zip(
        aisle_names,
        aisle_names[1:],
    ):
        connect(
            f"cross_aisle:south:{first_aisle}",
            f"cross_aisle:south:{second_aisle}",
        )
        connect(
            f"cross_aisle:north:{first_aisle}",
            f"cross_aisle:north:{second_aisle}",
        )
    connect("dispatch", f"cross_aisle:south:{aisle_names[0]}")
    connect("staging", f"cross_aisle:north:{aisle_names[0]}")

    for rack in racks:
        try:
            snapshot.path_from_dispatch(rack.aisle, rack.bay)
            snapshot.path_from_staging(rack.aisle, rack.bay)
        except WarehouseNavigationRouteError as exc:
            raise WarehouseNavigationConfigurationError(
                f"Rack {rack.aisle}/{rack.bay} is unreachable"
            ) from exc
    return snapshot


def segment_intersects_aabb(
    start_x_m: Decimal,
    start_y_m: Decimal,
    end_x_m: Decimal,
    end_y_m: Decimal,
    bounds: AxisAlignedBounds,
) -> bool:
    """Return whether a closed 2D segment intersects a closed AABB."""
    delta_x = end_x_m - start_x_m
    delta_y = end_y_m - start_y_m
    minimum_t = ZERO
    maximum_t = Decimal("1")
    for start, delta, lower, upper in (
        (start_x_m, delta_x, bounds.min_x_m, bounds.max_x_m),
        (start_y_m, delta_y, bounds.min_y_m, bounds.max_y_m),
    ):
        if delta == 0:
            if start < lower or start > upper:
                return False
            continue
        first_t = (lower - start) / delta
        second_t = (upper - start) / delta
        entry_t = min(first_t, second_t)
        exit_t = max(first_t, second_t)
        minimum_t = max(minimum_t, entry_t)
        maximum_t = min(maximum_t, exit_t)
        if minimum_t > maximum_t:
            return False
    return maximum_t >= ZERO and minimum_t <= Decimal("1")


def _segment_length_m(
    first: NavigationNode,
    second: NavigationNode,
) -> Decimal:
    delta_x = first.x_m - second.x_m
    delta_y = first.y_m - second.y_m
    return (delta_x * delta_x + delta_y * delta_y).sqrt()


def _natural_code_key(value: str) -> tuple[str, int, str]:
    match = re.search(r"(\d+)$", value)
    if match is None:
        return value, -1, value
    return value[: match.start()], int(match.group(1)), value
