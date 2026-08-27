// Substation coordinates for the transmission grid map.
//
// Provenance is tracked per entry so the map can be honest about accuracy:
//   official  - surveyed coordinate supplied by the transmission team (authoritative)
//   osm       - OpenStreetMap `power=substation` feature, verified against the real asset
//   colocated - shares a campus with another entry (e.g. the HVDC terminal at a pooling station)
//   approx    - town/area centroid only; the substation itself is not confidently located
//
// `aliases` hold the exact labels used in tc_network_node so lookup is an exact match
// rather than a substring guess. Substring matching remains only as a last resort.
//
// Velgaon (MH) and Hvdc Terminal (HVDC) are deliberately absent: no coordinate was
// supplied and neither is mapped in OSM. Lines touching them stay in the "not shown" count.

export type CoordSource = "official" | "osm" | "colocated" | "approx";

export interface SubstationCoord {
  name: string;
  lat: number;
  lng: number;
  /** Highest voltage class in kV, used for marker weighting. */
  kv?: number;
  source: CoordSource;
  aliases?: string[];
}

export const SUBSTATION_COORDS: SubstationCoord[] = [
  // ---- Khavda corridor -----------------------------------------------------
  { name: "Kps-I", lat: 24.098861, lng: 69.341197, kv: 765, source: "official" },
  { name: "Kps-II", lat: 24.078394, lng: 69.524972, kv: 765, source: "official" },
  { name: "Kps-II (HVDC)", lat: 24.078394, lng: 69.524972, kv: 765, source: "colocated" },
  { name: "Kps-III", lat: 24.205069, lng: 69.498081, kv: 765, source: "official" },
  { name: "Kps-III (HVDC)", lat: 24.205069, lng: 69.498081, kv: 765, source: "colocated" },
  { name: "Ahmedabad", lat: 22.980889, lng: 72.179936, kv: 765, source: "official" },
  { name: "Babhaleswar", lat: 19.619753, lng: 74.493142, kv: 400, source: "official" },
  { name: "Boisar-II (GIS)", lat: 19.830000, lng: 72.760000, kv: 400, source: "official" },
  { name: "Narendra (NEW)", lat: 16.551353, lng: 75.853386, kv: 400, source: "official" },
  { name: "Navsari (NEW)", lat: 21.007322, lng: 72.760292, kv: 765, source: "official" },
  { name: "Padghe (M)", lat: 19.363056, lng: 73.189167, kv: 400, source: "official" },
  { name: "Nagpur (HVDC)", lat: 20.950000, lng: 79.010000, kv: 800, source: "official" },
  { name: "South Olpad", lat: 21.147525, lng: 73.027531, kv: 400, source: "official" },
  { name: "South Olpad (GIS)", lat: 21.147525, lng: 73.027531, kv: 400, source: "colocated" },
  { name: "Vataman", lat: 22.492778, lng: 72.337361, kv: 400, source: "official" },

  { name: "Padghe (PG)", lat: 19.4079, lng: 73.2122, kv: 765, source: "osm" },
  { name: "Pirana (T)", lat: 22.9268, lng: 72.5569, kv: 400, source: "osm" },
  { name: "Lilo Pirana (PG)", lat: 22.9268, lng: 72.5569, kv: 400, source: "colocated" },
  { name: "Banaskantha", lat: 24.1389, lng: 71.9994, kv: 765, source: "osm" },
  { name: "Bhuj-I", lat: 23.3633, lng: 69.1571, kv: 765, source: "osm" },
  { name: "Halvad", lat: 23.0118, lng: 71.2118, kv: 220, source: "osm" },
  { name: "Hazira", lat: 21.1172, lng: 72.6328, kv: 400, source: "osm" },
  { name: "Hinjewadi", lat: 18.5858, lng: 73.7374, kv: 220, source: "osm" },
  { name: "Koyna", lat: 17.4861, lng: 73.5936, kv: 400, source: "osm" },
  { name: "Lakadia", lat: 23.3932, lng: 70.5954, kv: 765, source: "osm" },
  { name: "Pune (GIS)", lat: 18.7185, lng: 74.1658, kv: 765, source: "osm" },
  { name: "Pune-III (GIS)", lat: 18.7185, lng: 74.1658, kv: 765, source: "colocated" },
  { name: "Raipur", lat: 21.2455, lng: 81.4855, kv: 400, source: "osm" },
  { name: "Vadodara", lat: 22.3174, lng: 73.3772, kv: 765, source: "osm" },
  { name: "Wardha", lat: 20.6704, lng: 78.4930, kv: 765, source: "osm" },

  { name: "Ghandhar", lat: 21.9333, lng: 72.8333, kv: 400, source: "approx" },
  { name: "Nagpur", lat: 21.1458, lng: 79.0882, kv: 400, source: "approx" },

  // ---- Rajasthan corridor --------------------------------------------------
  { name: "Beawar", lat: 26.1999, lng: 74.1295, kv: 765, source: "osm" },
  { name: "Bhopal", lat: 23.4018, lng: 77.4462, kv: 765, source: "osm" },
  { name: "Bikaner-III", lat: 28.2495, lng: 73.3821, kv: 765, source: "osm" },
  { name: "Fatehgarh-III", lat: 26.3522, lng: 71.1024, kv: 765, source: "osm" },
  { name: "Indore", lat: 22.9084, lng: 75.9035, kv: 765, source: "osm" },
  { name: "Jhatikara", lat: 28.5346, lng: 76.9366, kv: 765, source: "osm" },
  { name: "Kanpur", lat: 26.3866, lng: 80.0495, kv: 765, source: "osm" },
  { name: "Khandwa", lat: 22.2008, lng: 76.0268, kv: 765, source: "osm" },
  { name: "Khetri", lat: 28.0342, lng: 75.7080, kv: 765, source: "osm" },
  { name: "Mandsaur", lat: 24.0001, lng: 75.3582, kv: 400, source: "osm" },
  { name: "Narela", lat: 28.8231, lng: 76.9854, kv: 765, source: "osm" },
  { name: "Ramgarh", lat: 27.3326, lng: 70.5425, kv: 400, source: "osm", aliases: ["Ramgarh-II"] },
  { name: "Sikar-II", lat: 27.5347, lng: 75.3791, kv: 765, source: "osm" },
  { name: "Varanasi", lat: 25.2796, lng: 82.6906, kv: 765, source: "osm" },

  // Located in OSM only at a lower voltage than the project scope implies - treat as indicative.
  { name: "Bhadla", lat: 27.5274, lng: 71.9455, kv: 220, source: "approx", aliases: ["Bhadla-III", "Bhadla-LV"] },
  { name: "Dwarka", lat: 28.5796, lng: 77.0430, kv: 220, source: "approx" },
  { name: "Fatehpur", lat: 27.9847, lng: 74.9581, kv: 132, source: "approx" },
  { name: "Kurawar", lat: 23.5240, lng: 77.0306, kv: 132, source: "approx" },
  { name: "Sirohi", lat: 24.8668, lng: 72.8336, kv: 220, source: "approx" },
];

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

// Exact-match index over canonical names and aliases.
const EXACT = new Map<string, SubstationCoord>();
for (const sub of SUBSTATION_COORDS) {
  EXACT.set(normalize(sub.name), sub);
  for (const alias of sub.aliases ?? []) EXACT.set(normalize(alias), sub);
}

// Longest name first so a specific entry wins over a shorter generic prefix.
const SORTED_COORDS = [...SUBSTATION_COORDS].sort((a, b) => b.name.length - a.name.length);

export function findSubstationCoord(label?: string | null): SubstationCoord | null {
  if (!label) return null;
  const norm = normalize(label);
  const exact = EXACT.get(norm);
  if (exact) return exact;
  for (const sub of SORTED_COORDS) {
    if (norm.includes(normalize(sub.name))) return sub;
  }
  return null;
}

export const SOURCE_LABEL: Record<CoordSource, string> = {
  official: "Surveyed coordinate",
  osm: "OpenStreetMap verified",
  colocated: "Co-located with adjacent station",
  approx: "Approximate area only",
};
