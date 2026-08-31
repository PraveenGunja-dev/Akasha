"""Populate tc_line_geometry with real transmission-line routes.

tc_network_edge records only the two substations a line joins, so the grid map can
draw nothing but a straight chord between them. This script fetches traced
`power=line` ways from OpenStreetMap and matches them to those edges, giving each
line its actual alignment.

For each edge the matcher searches the OSM line graph for a route between the two
substations, widening the attachment radius only as far as it takes to find one that
stays inside the corridor. Every accepted route must sit within both a length budget and
a maximum bow away from the direct chord, so a path that wanders onto a neighbouring
right-of-way is rejected rather than drawn.

Confidence records how much help the trace needed:

  high   - a short chain found at the tight radius, on ways of the stated voltage,
           close to the direct distance
  medium - a longer chain, or one found only after widening the attachment radius
  low    - relies on a way whose tagged voltage contradicts the edge, or is much
           longer than the direct distance; plausible but unverified

Anything else is left unmatched and keeps its straight-chord fallback on the map.

Usage:
    python scripts/ingest_line_geometry.py --region Khavda
    python scripts/ingest_line_geometry.py --region all --dry-run
    python scripts/ingest_line_geometry.py --region all --cache-only   # reuse saved OSM data

OSM data is cached under scripts/.osm_cache/ so re-runs do not re-hit Overpass.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models import TcLineGeometry, TcNetworkEdge  # noqa: E402

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".osm_cache")
GRID_COORDS_TS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "src", "features", "analytics", "transmission", "gridCoords.ts",
)

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# How close a way must pass to a substation to count as terminating there, tried in
# order and stopping at the first radius that routes. Substation coordinates are campus
# centroids while lines end at a boundary bay, so a tight radius alone misses most
# corridors; a wide one alone lets a route start on an unrelated line that happens to
# pass nearby. Escalating keeps the tight, trustworthy match wherever one exists and
# only reaches wider for edges that would otherwise fall back to a straight chord.
TERMINAL_RADII_KM = (8.0, 12.0, 18.0, 25.0)
# Ways whose endpoints are within this distance are treated as electrically joined.
JOIN_TOLERANCE_KM = 0.35
# Reject a routed chain longer than this multiple of the direct substation distance.
MAX_DETOUR_FACTOR = 2.0
# Reject a route that bows further than this from the direct chord. Length alone does
# not catch a path that leaves the corridor and comes back: a detour out to a parallel
# line and back can sit inside the length budget while tracing the wrong right-of-way.
# The allowance grows with the link but is floored and capped, because a purely
# proportional bound is meaningless at both extremes - too tight for a 20 km hop between
# campus centroids, and wide enough on a 500 km link to admit a different corridor.
MIN_CORRIDOR_DEVIATION_KM = 12.0
MAX_CORRIDOR_DEVIATION_KM = 35.0
CORRIDOR_DEVIATION_FRACTION = 0.18
# A traced route must cover at least this much of the direct distance. Attaching within
# the terminal radius of both substations does not guarantee the way spans them: a
# corridor clipped short at each end is shorter than the chord it claims to follow, and
# would be drawn as a stub with a straight leap to each substation.
MIN_SPAN_FRACTION = 0.85
# When set, an OSM way may match an edge even if their stated voltages disagree.
IGNORE_VOLTAGE = False
# Douglas-Peucker tolerance for the stored path. OSM traces a line tower by tower, which
# is far more detail than a national-scale map can show; thinning to this keeps every
# visible bend while cutting the payload the map has to draw.
SIMPLIFY_TOLERANCE_KM = 0.12


# --------------------------------------------------------------------------- geo

def haversine_km(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def path_length_km(points) -> float:
    return sum(
        haversine_km(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def _project_km(point, origin):
    """Local flat-earth projection to km, good to well under a metre at corridor scale."""
    return ((point[1] - origin[1]) * 111.320 * math.cos(math.radians(origin[0])),
            (point[0] - origin[0]) * 110.574)


def point_to_chord_km(point, a, b) -> float:
    """Perpendicular distance from a point to the A-B chord, clamped to the segment."""
    px, py = _project_km(point, a)
    bx, by = _project_km(b, a)
    span = bx * bx + by * by
    if span == 0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / span))
    return math.hypot(px - t * bx, py - t * by)


def max_corridor_deviation_km(points, a, b) -> float:
    return max((point_to_chord_km(p, a, b) for p in points), default=0.0)


def simplify(points, tolerance_km: float):
    """Douglas-Peucker, iterative so a tower-by-tower trace cannot blow the stack."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        far_idx, far_dist = -1, tolerance_km
        for i in range(lo + 1, hi):
            d = point_to_chord_km(points[i], points[lo], points[hi])
            if d > far_dist:
                far_idx, far_dist = i, d
        if far_idx >= 0:
            keep[far_idx] = True
            stack.append((lo, far_idx))
            stack.append((far_idx, hi))
    return [p for p, k in zip(points, keep) if k]


def stitch_endpoints(points, a, b):
    """Anchor the traced path to the substation coordinates at either end.

    A route attaches to OSM wherever the corridor passes nearest the campus, which can
    be kilometres from the marker. Left as-is the drawn line floats away from the
    substation it serves; carrying it the last stretch is what makes the map read as a
    connected network rather than a scatter of loose strokes.
    """
    stitched = list(points)
    if haversine_km(a["lat"], a["lng"], *stitched[0]) > 0.05:
        stitched.insert(0, [a["lat"], a["lng"]])
    if haversine_km(b["lat"], b["lng"], *stitched[-1]) > 0.05:
        stitched.append([b["lat"], b["lng"]])
    return stitched


# ------------------------------------------------------------------ substations

def load_substation_coords() -> dict:
    """Parse the canonical coordinate table from gridCoords.ts.

    The frontend file is the single source of truth for substation positions, so it is
    read directly rather than duplicated here where the two copies could drift apart.
    """
    with open(GRID_COORDS_TS, encoding="utf-8") as f:
        src = f.read()
    body = src.split("SUBSTATION_COORDS: SubstationCoord[] = [", 1)[1].split("\n];", 1)[0]

    coords, aliases = {}, {}
    pattern = r'name:\s*"(.*?)".*?lat:\s*([-\d.]+),\s*lng:\s*([-\d.]+)(.*?)\},'
    for m in re.finditer(pattern, body, re.S):
        name, lat, lng, rest = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4)
        kv = re.search(r"kv:\s*(\d+)", rest)
        entry = {"name": name, "lat": lat, "lng": lng, "kv": int(kv.group(1)) if kv else None}
        coords[normalize(name)] = entry
        alias_block = re.search(r"aliases:\s*\[(.*?)\]", rest)
        if alias_block:
            for alias in re.findall(r'"(.*?)"', alias_block.group(1)):
                aliases[normalize(alias)] = entry
    coords.update(aliases)
    return coords


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def find_coord(coords: dict, label: str):
    key = normalize(label)
    if key in coords:
        return coords[key]
    for name in sorted(coords, key=len, reverse=True):
        if name and name in key:
            return coords[name]
    return None


def parse_kv(value) -> int | None:
    """'765 kV' -> 765, '400000' -> 400, '765000;400000' -> 765."""
    if not value:
        return None
    nums = [int(n) for n in re.findall(r"\d+", str(value))]
    if not nums:
        return None
    best = max(nums)
    return best // 1000 if best >= 1000 else best


# --------------------------------------------------------------------- overpass

def overpass(query: str):
    last = None
    for attempt in range(5):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            req = urllib.request.Request(
                endpoint,
                data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "akasha-line-geometry-ingest"},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.load(resp)["elements"]
        except Exception as exc:  # noqa: BLE001 - retry any transport/timeout failure
            last = exc
            print(f"    overpass attempt {attempt + 1} failed ({exc}); retrying...")
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"Overpass unavailable after retries: {last}")


def fetch_lines(region: str, bbox, cache_only: bool):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"lines_{region.lower()}.json")
    if os.path.exists(cache_path):
        print(f"  using cached OSM lines: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    if cache_only:
        print(f"  no cache for {region} and --cache-only set; skipping")
        return []

    south, west, north, east = bbox
    # Restricted to transmission voltages: an unfiltered power=line query over a corridor
    # this size pulls tens of thousands of distribution feeders that can never match.
    query = (
        f"[out:json][timeout:600];"
        f'way["power"="line"]["voltage"~"^(220000|230000|400000|500000|765000|800000)"]'
        f"({south:.4f},{west:.4f},{north:.4f},{east:.4f});"
        f"out geom;"
    )
    print(f"  querying Overpass for {region} bbox {south:.2f},{west:.2f},{north:.2f},{east:.2f} ...")
    elements = overpass(query)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(elements, f)
    print(f"  cached {len(elements)} ways -> {cache_path}")
    return elements


# ---------------------------------------------------------------------- routing

class LineNetwork:
    """Connected graph of OSM power-line ways, searchable between two substations.

    Graph nodes are way endpoints. Substations attach to the network at the nearest
    *vertex* of any nearby way rather than only at its endpoints: OSM splits ways at
    arbitrary points, so a line running straight through a substation frequently has
    its endpoints tens of kilometres away. Attaching mid-way and slicing the geometry
    is what makes most edges matchable at all.
    """

    # Vertex lookup grid, ~5.5 km per cell.
    CELL = 0.05

    def __init__(self, ways):
        self.segments = []
        for way in ways:
            geom = way.get("geometry") or []
            if len(geom) < 2:
                continue
            points = [[p["lat"], p["lon"]] for p in geom]
            cumulative = [0.0]
            for i in range(len(points) - 1):
                cumulative.append(
                    cumulative[-1] + haversine_km(points[i][0], points[i][1],
                                                  points[i + 1][0], points[i + 1][1])
                )
            self.segments.append({
                "id": way["id"],
                "points": points,
                "cum": cumulative,
                "kv": parse_kv(way.get("tags", {}).get("voltage")),
                "length": cumulative[-1],
            })

        # node key -> [(neighbour key, cost, segment idx, forward?)]
        self.adj = defaultdict(list)
        # grid cell -> [(segment idx, vertex idx)]
        self.vertex_grid = defaultdict(list)
        for idx, seg in enumerate(self.segments):
            a, b = self._key(seg["points"][0]), self._key(seg["points"][-1])
            self.adj[a].append((b, seg["length"], idx, True))
            self.adj[b].append((a, seg["length"], idx, False))
            for vi, point in enumerate(seg["points"]):
                self.vertex_grid[self._cell(point)].append((idx, vi))

    @staticmethod
    def _key(point):
        # ~110 m rounding: connected OSM ways share a node exactly, and this also
        # absorbs the small gaps left where a mapper did not quite join two ways.
        return (round(point[0], 3), round(point[1], 3))

    @classmethod
    def _cell(cls, point):
        return (int(point[0] / cls.CELL), int(point[1] / cls.CELL))

    def attachments(self, lat, lng, radius_km, want_kv):
        """Nearest vertex per nearby way, as {segment idx: (vertex idx, gap km)}.

        The gap is carried because it is a real cost. A way clipped short of the
        substation gets picked up just as readily as one that runs right into it, and
        without charging for the leftover distance the search prefers the clipped way -
        it is literally shorter.
        """
        span = int(radius_km / (111.0 * self.CELL)) + 1
        base = self._cell([lat, lng])
        best_per_segment = {}
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                for seg_idx, vi in self.vertex_grid.get((base[0] + dx, base[1] + dy), ()):
                    seg = self.segments[seg_idx]
                    point = seg["points"][vi]
                    d = haversine_km(lat, lng, point[0], point[1])
                    if d > radius_km:
                        continue
                    if seg_idx not in best_per_segment or d < best_per_segment[seg_idx][0]:
                        best_per_segment[seg_idx] = (d, vi)
        return {seg_idx: (vi, d) for seg_idx, (d, vi) in best_per_segment.items()}

    def _slice(self, seg_idx, vi, to_end: bool):
        """Geometry and cost from a mid-way vertex out to one end of that way."""
        seg = self.segments[seg_idx]
        if to_end:
            return seg["points"][vi:], seg["length"] - seg["cum"][vi]
        return list(reversed(seg["points"][: vi + 1])), seg["cum"][vi]

    # Search-cost multiplier for a way whose tagged voltage contradicts the edge.
    # Voltage is a preference, not a veto: OSM tags a corridor inconsistently along its
    # length, so a hard stop rejects routes that are otherwise plainly correct. Routes
    # that rely on such a way are reported at 'low' confidence.
    VOLTAGE_PENALTY = 4.0

    def _penalty(self, seg, want_kv):
        return self.VOLTAGE_PENALTY if (want_kv and seg["kv"] and seg["kv"] != want_kv) else 1.0

    def route(self, a, b, max_km, want_kv, radius_km, max_deviation_km=math.inf):
        """Shortest real-world route between two substations, or None.

        The search is confined to a corridor `max_deviation_km` either side of the
        direct A-B chord. Constraining the search rather than filtering its answer
        matters: Dijkstra returns only the cheapest route, so a wandering path that
        happens to be shortest would otherwise mask a slightly longer one that
        follows the right corridor, and the edge would be discarded with it.

        Returns (points, real_km, hops, used_mismatched_voltage).
        """
        starts = self.attachments(a["lat"], a["lng"], radius_km, want_kv)
        goals = self.attachments(b["lat"], b["lng"], radius_km, want_kv)
        if not starts or not goals:
            return None

        chord_a = (a["lat"], a["lng"])
        chord_b = (b["lat"], b["lng"])

        def strays(points):
            return any(point_to_chord_km(p, chord_a, chord_b) > max_deviation_km
                       for p in points)

        # Both substations sit on one continuous way - slice it and we are done.
        for seg_idx, (vi, gap_a) in starts.items():
            if seg_idx in goals:
                vj, gap_b = goals[seg_idx]
                if vi == vj:
                    continue
                seg = self.segments[seg_idx]
                lo, hi = min(vi, vj), max(vi, vj)
                points = seg["points"][lo: hi + 1]
                real = seg["cum"][hi] - seg["cum"][lo] + gap_a + gap_b
                if real <= max_km and not strays(points):
                    off = self._penalty(seg, want_kv) > 1.0
                    return (points if vi < vj else list(reversed(points))), real, 1, off

        # Cost of finishing at B from each graph node that touches a goal way.
        finish = defaultdict(list)
        for seg_idx, (vi, gap_b) in goals.items():
            seg = self.segments[seg_idx]
            penalty = self._penalty(seg, want_kv)
            for to_end in (False, True):
                points, slice_km = self._slice(seg_idx, vi, to_end)
                if strays(points):
                    continue
                real = slice_km + gap_b
                node = self._key(seg["points"][-1] if to_end else seg["points"][0])
                # points run outward from B, so reverse them to run toward B.
                finish[node].append((real * penalty, real, list(reversed(points)), penalty > 1.0))

        # Heap entries are (search cost, real km, node, geometry, hops, voltage mismatch).
        # Search cost carries the voltage penalty; the budget is checked against real km.
        queue = []
        for seg_idx, (vi, gap_a) in starts.items():
            seg = self.segments[seg_idx]
            penalty = self._penalty(seg, want_kv)
            for to_end in (True, False):
                points, slice_km = self._slice(seg_idx, vi, to_end)
                real = slice_km + gap_a
                if real > max_km or strays(points):
                    continue
                node = self._key(seg["points"][-1] if to_end else seg["points"][0])
                queue.append((real * penalty, real, node, points, 1, penalty > 1.0))
        heapq.heapify(queue)

        best = {}
        while queue:
            cost, real, node, points, hops, off_voltage = heapq.heappop(queue)
            # Enforced before the goal test: a route only counts if it is inside the
            # detour budget, otherwise Dijkstra happily returns a wandering path.
            if real > max_km or best.get(node, math.inf) <= cost:
                continue
            best[node] = cost

            for finish_cost, finish_real, finish_points, finish_off in finish.get(node, ()):
                if real + finish_real <= max_km:
                    return (self._join(points, finish_points), real + finish_real,
                            hops + 1, off_voltage or finish_off)

            for neighbour, seg_km, seg_idx, forward in self.adj[node]:
                seg = self.segments[seg_idx]
                penalty = self._penalty(seg, want_kv)
                nxt_real = real + seg_km
                nxt_cost = cost + seg_km * penalty
                if nxt_real > max_km or best.get(neighbour, math.inf) <= nxt_cost:
                    continue
                ordered = seg["points"] if forward else list(reversed(seg["points"]))
                if strays(ordered):
                    continue
                heapq.heappush(queue, (nxt_cost, nxt_real, neighbour,
                                       self._join(points, ordered), hops + 1,
                                       off_voltage or penalty > 1.0))
        return None

    @staticmethod
    def _join(head, tail):
        if head and tail and haversine_km(*head[-1], *tail[0]) < JOIN_TOLERANCE_KM:
            return head + tail[1:]
        return head + tail


# ------------------------------------------------------------------------- main

def bbox_for(points, margin_deg=0.6):
    lats = [p["lat"] for p in points]
    lngs = [p["lng"] for p in points]
    return (min(lats) - margin_deg, min(lngs) - margin_deg,
            max(lats) + margin_deg, max(lngs) + margin_deg)


def process_region(session, region, coords, cache_only, dry_run):
    edges = session.query(TcNetworkEdge).filter(TcNetworkEdge.region == region).all()
    seen, unique = set(), []
    for e in edges:
        if e.edge_id not in seen:
            seen.add(e.edge_id)
            unique.append(e)

    located = []
    for edge in unique:
        a = find_coord(coords, edge.from_label)
        b = find_coord(coords, edge.to_label)
        if a and b and (a["lat"], a["lng"]) != (b["lat"], b["lng"]):
            located.append((edge, a, b))

    print(f"\n=== {region}: {len(unique)} edges, {len(located)} with two distinct endpoints ===")
    if not located:
        return 0, 0

    endpoints = [a for _, a, _ in located] + [b for _, _, b in located]
    ways = fetch_lines(region, bbox_for(endpoints), cache_only)
    if not ways:
        return 0, len(located)

    network = LineNetwork(ways)
    print(f"  {len(network.segments)} usable line segments, {len(network.adj)} junctions")

    matched = rejected_guard = 0
    for edge, a, b in located:
        direct_km = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
        want_kv = None if IGNORE_VOLTAGE else parse_kv(edge.voltage)
        # Short links need absolute headroom, not just a ratio: a 14 km hop cannot be
        # expected to route within 1.7x when substation coordinates are campus centroids.
        budget = max(direct_km * MAX_DETOUR_FACTOR, direct_km + 25)
        max_deviation = min(MAX_CORRIDOR_DEVIATION_KM,
                            max(MIN_CORRIDOR_DEVIATION_KM,
                                direct_km * CORRIDOR_DEVIATION_FRACTION))
        min_span = direct_km * MIN_SPAN_FRACTION

        # Widen the attachment radius only as far as it takes to find a corridor-bound
        # route, so a tight, trustworthy match is never traded away for a loose one.
        chosen = None
        for radius in TERMINAL_RADII_KM:
            result = network.route(a, b, budget, want_kv, radius, max_deviation)
            if result and len(result[0]) >= 2 and result[1] >= min_span:
                chosen = (result, radius)
                break
        if not chosen:
            # Distinguish "no acceptable route" from "no route at all" so the run log
            # says whether the guards or the data is what left this edge straight.
            if any(network.route(a, b, budget, want_kv, r) for r in TERMINAL_RADII_KM):
                rejected_guard += 1
            continue

        (points, cost, hops, off_voltage), radius = chosen
        deviation = max_corridor_deviation_km(points, (a["lat"], a["lng"]),
                                              (b["lat"], b["lng"]))
        ratio = cost / direct_km if direct_km else 1.0
        # Confidence describes how much the trace had to be helped along. A clean match
        # is a short chain, found at the tight radius, on ways whose voltage agrees, and
        # close to the direct distance; each concession the matcher had to make is a
        # reason to present the route as plausible rather than verified.
        if off_voltage or radius > 15.0 or ratio > 1.5:
            confidence = "low"
        elif hops <= 2 and radius <= 8.0 and ratio <= 1.25:
            confidence = "high"
        else:
            confidence = "medium"

        points = stitch_endpoints(simplify(points, SIMPLIFY_TOLERANCE_KM), a, b)
        matched += 1

        if dry_run:
            print(f"    {edge.from_label} -> {edge.to_label}: "
                  f"{len(points)} pts, {cost:.0f} km (direct {direct_km:.0f}, {ratio:.2f}x), "
                  f"dev {deviation:.0f} km, r{radius:.0f}, {confidence}")
            continue

        session.query(TcLineGeometry).filter(
            TcLineGeometry.edge_id == edge.edge_id,
            TcLineGeometry.region == region,
        ).delete()
        session.add(TcLineGeometry(
            region=region,
            edge_id=edge.edge_id,
            path=json.dumps([[round(p[0], 5), round(p[1], 5)] for p in points]),
            point_count=len(points),
            length_km=round(cost, 2),
            source="osm",
            source_ref=f"{hops} osm way(s), attach {radius:.0f} km",
            voltage=edge.voltage,
            match_confidence=confidence,
        ))

    if not dry_run:
        session.commit()
    if rejected_guard:
        print(f"  {rejected_guard} candidate route(s) rejected as off-corridor or too short")
    return matched, len(located)


def main():
    global TERMINAL_RADII_KM, MAX_DETOUR_FACTOR, IGNORE_VOLTAGE

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="all", help="Khavda | Rajasthan | all")
    parser.add_argument("--dry-run", action="store_true", help="report matches without writing")
    parser.add_argument("--cache-only", action="store_true", help="never call Overpass")
    parser.add_argument("--terminal-radius", type=float, default=None,
                        help="pin the attach radius in km instead of escalating through "
                             f"{', '.join(str(r) for r in TERMINAL_RADII_KM)}")
    parser.add_argument("--detour", type=float, default=MAX_DETOUR_FACTOR,
                        help="reject routes longer than this multiple of the direct distance")
    parser.add_argument("--ignore-voltage", action="store_true",
                        help="do not require the OSM way voltage to match the edge")
    args = parser.parse_args()

    if args.terminal_radius is not None:
        TERMINAL_RADII_KM = (args.terminal_radius,)
    MAX_DETOUR_FACTOR = args.detour
    IGNORE_VOLTAGE = args.ignore_voltage

    regions = ["Khavda", "Rajasthan"] if args.region == "all" else [args.region]

    engine = create_engine(os.getenv("DATABASE_URL"))
    TcLineGeometry.__table__.create(bind=engine, checkfirst=True)
    session = sessionmaker(bind=engine)()

    coords = load_substation_coords()
    print(f"loaded {len(coords)} substation coordinate keys from gridCoords.ts")

    total_matched = total_candidates = 0
    try:
        for region in regions:
            matched, candidates = process_region(session, region, coords, args.cache_only, args.dry_run)
            total_matched += matched
            total_candidates += candidates
            pct = (matched / candidates * 100) if candidates else 0
            print(f"  -> {matched}/{candidates} routed ({pct:.0f}%)")
    finally:
        session.close()

    verb = "would route" if args.dry_run else "routed"
    print(f"\n{verb} {total_matched}/{total_candidates} edges with real OSM geometry")
    if total_candidates and not args.dry_run:
        print("Unmatched edges keep their straight-chord fallback on the map.")


if __name__ == "__main__":
    main()
