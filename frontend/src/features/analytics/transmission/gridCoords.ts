// Substation coordinates for the transmission grid map.
//
// Provenance is tracked per entry so the map can be honest about accuracy:
//   official  - surveyed coordinate supplied by the transmission team (authoritative;
//               re-checked against their substation list 2026-10-10 - 27 entries corrected,
//               e.g. South Olpad was 89 km and KPS-III 15 km off)
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
  { name: "Kps-I", lat: 24.10028, lng: 69.33702, kv: 765, source: "official" },
  { name: "Kps-II", lat: 24.08249, lng: 69.51703, kv: 765, source: "official" },
  { name: "Kps-II (HVDC)", lat: 24.08249, lng: 69.61554, kv: 765, source: "official" },
  { name: "Kps-III", lat: 24.06716, lng: 69.47434, kv: 765, source: "official" },
  { name: "Kps-III (HVDC)", lat: 24.06716, lng: 69.57284, kv: 765, source: "official" },
  { name: "Ahmedabad", lat: 22.980889, lng: 72.179936, kv: 765, source: "official" },
  { name: "Babhaleswar", lat: 19.619753, lng: 74.493142, kv: 400, source: "official" },
  { name: "Boisar-II (GIS)", lat: 19.830000, lng: 72.760000, kv: 400, source: "official" },
  { name: "Narendra (NEW)", lat: 16.551353, lng: 75.853386, kv: 400, source: "official" },
  { name: "Navsari (NEW)", lat: 21.007322, lng: 72.760292, kv: 765, source: "official" },
  { name: "Padghe (M)", lat: 19.363056, lng: 73.189167, kv: 400, source: "official" },
  { name: "Nagpur (HVDC)", lat: 20.950000, lng: 79.010000, kv: 800, source: "official" },
  { name: "South Olpad", lat: 21.94600, lng: 73.08565, kv: 400, source: "official" },
  { name: "South Olpad (GIS)", lat: 21.94600, lng: 73.08565, kv: 400, source: "official" },
  { name: "Vataman", lat: 22.492778, lng: 72.337361, kv: 400, source: "official" },

  { name: "Padghe (PG)", lat: 19.40886, lng: 73.21122, kv: 765, source: "official" },
  { name: "Pirana (T)", lat: 22.96690, lng: 72.59750, kv: 400, source: "official" },
  { name: "Lilo Pirana (PG)", lat: 22.9268, lng: 72.5569, kv: 400, source: "colocated" },
  { name: "Banaskantha", lat: 24.13765, lng: 71.99890, kv: 765, source: "official" },
  { name: "Bhuj-I", lat: 23.45257, lng: 69.59224, kv: 765, source: "official" },
  { name: "Halvad", lat: 22.91108, lng: 71.23059, kv: 220, source: "official" },
  { name: "Hazira", lat: 21.1172, lng: 72.6328, kv: 400, source: "osm" },
  { name: "Hinjewadi", lat: 18.5858, lng: 73.7374, kv: 220, source: "osm" },
  { name: "Koyna", lat: 17.4861, lng: 73.5936, kv: 400, source: "osm" },
  { name: "Lakadia", lat: 23.39399, lng: 70.59772, kv: 765, source: "official" },
  { name: "Pune (GIS)", lat: 18.79438, lng: 73.69815, kv: 765, source: "official" },
  { name: "Pune-III (GIS)", lat: 18.7185, lng: 74.1658, kv: 765, source: "colocated" },
  { name: "Raipur", lat: 21.23333, lng: 81.48333, kv: 400, source: "official" },
  { name: "Vadodara", lat: 22.3174, lng: 73.3772, kv: 765, source: "osm" },
  { name: "Wardha", lat: 20.6704, lng: 78.4930, kv: 765, source: "osm" },

  { name: "Ghandhar", lat: 21.9333, lng: 72.8333, kv: 400, source: "approx" },
  { name: "Nagpur", lat: 21.1458, lng: 79.0882, kv: 400, source: "approx" },

  // ---- Rajasthan corridor --------------------------------------------------
  { name: "Beawar", lat: 26.1999, lng: 74.1295, kv: 765, source: "osm" },
  { name: "Bhopal", lat: 23.4018, lng: 77.4462, kv: 765, source: "osm" },
  { name: "Bikaner-III", lat: 28.37293, lng: 73.17076, kv: 765, source: "official" },
  { name: "Fatehgarh-III", lat: 26.35007, lng: 71.10011, kv: 765, source: "official" },
  { name: "Indore", lat: 22.90884, lng: 75.89969, kv: 765, source: "official" },
  { name: "Jhatikara", lat: 28.53223, lng: 76.93624, kv: 765, source: "official" },
  { name: "Kanpur", lat: 26.3866, lng: 80.0495, kv: 765, source: "osm" },
  { name: "Khandwa", lat: 21.83240, lng: 76.40400, kv: 765, source: "official" },
  { name: "Khetri", lat: 28.03292, lng: 75.70930, kv: 765, source: "official" },
  { name: "Mandsaur", lat: 24.20664, lng: 75.17084, kv: 400, source: "official" },
  { name: "Narela", lat: 28.82341, lng: 76.98380, kv: 765, source: "official" },
  { name: "Ramgarh", lat: 27.47146, lng: 70.49399, kv: 400, source: "official", aliases: ["Ramgarh-II"] },
  { name: "Sikar-II", lat: 27.69534, lng: 75.08824, kv: 765, source: "official" },
  { name: "Varanasi", lat: 25.2796, lng: 82.6906, kv: 765, source: "osm" },

  // Located in OSM only at a lower voltage than the project scope implies - treat as indicative.
  { name: "Bhadla", lat: 27.41940, lng: 72.07220, kv: 220, source: "official", aliases: ["Bhadla-III", "Bhadla-LV"] },
  { name: "Dwarka", lat: 28.5796, lng: 77.0430, kv: 220, source: "approx" },
  { name: "Fatehpur", lat: 27.9847, lng: 74.9581, kv: 132, source: "approx" },
  { name: "Kurawar", lat: 23.5240, lng: 77.0306, kv: 132, source: "approx" },
  { name: "Sirohi", lat: 25.08370, lng: 72.79340, kv: 220, source: "official" },

  // ---- From the transmission team's substation list (2026-10-10) ---------
  // Same source as the corrected entries above (training_model/reference/substations_dms.tsv).
  { name: "Pirana (PG)", lat: 22.92760, lng: 72.55684, source: "official" },
  { name: "Pirana PGCIL", lat: 22.92856, lng: 72.55688, source: "official" },
  { name: "Boisar-II (Sec-II)", lat: 19.79452, lng: 72.78501, source: "official" },
  { name: "Boisar-II - Pune-III", lat: 24.20738, lng: 69.49487, source: "official" },
  { name: "Bhadla-3", lat: 27.67231, lng: 72.20655, source: "official" },
  { name: "Jam Khambhaliya (GIS) PS", lat: 22.14470, lng: 69.67720, source: "official" },
  { name: "Bhuj PS", lat: 23.45580, lng: 69.56240, source: "official" },
  { name: "Bhuj-II PS", lat: 23.37210, lng: 69.14410, source: "official" },
  { name: "Bhachau", lat: 23.20610, lng: 70.18730, source: "official" },
  { name: "Banaskantha (Radhanesda) PS [GIS]", lat: 24.34300, lng: 71.48730, source: "official" },
  { name: "Raghanesda", lat: 24.45100, lng: 71.40960, source: "official" },
  { name: "Rajgarh (PG)", lat: 22.68220, lng: 74.92440, source: "official" },
  { name: "Pachora PS", lat: 23.71770, lng: 76.12330, source: "official" },
  { name: "Neemuch PS", lat: 25.02520, lng: 75.22740, source: "official" },
  { name: "Kallam PS", lat: 18.62250, lng: 75.87140, source: "official" },
  { name: "Parli (PG)", lat: 18.74140, lng: 76.42820, source: "official" },
  { name: "Solapur (PG)", lat: 17.60870, lng: 76.05000, source: "official" },
  { name: "Solapur PS", lat: 17.88590, lng: 76.21370, source: "official" },
  { name: "Dhule PS", lat: 20.97960, lng: 74.15080, source: "official" },
  { name: "Ishanagar", lat: 24.86270, lng: 79.36840, source: "official" },
  { name: "Morena PS", lat: 25.91330, lng: 77.49900, source: "official" },
  { name: "Tuticorin-II", lat: 9.05060, lng: 77.92540, source: "official" },
  { name: "Pugalur", lat: 10.96170, lng: 77.92280, source: "official" },
  { name: "Palakkad", lat: 10.77280, lng: 76.76000, source: "official" },
  { name: "Pavagada", lat: 14.31860, lng: 77.38550, source: "official" },
  { name: "Hiriyur", lat: 13.95340, lng: 76.53650, source: "official" },
  { name: "Kurnool(new)", lat: 15.67460, lng: 78.17650, source: "official" },
  { name: "Koppal", lat: 15.36540, lng: 75.99020, source: "official" },
  { name: "Karur", lat: 10.84280, lng: 77.65910, source: "official" },
  { name: "Gadag", lat: 15.78490, lng: 75.85780, source: "official" },
  { name: "Koppal-II PS", lat: 15.56770, lng: 76.11740, source: "official" },
  { name: "Gadag-II PS", lat: 15.37940, lng: 75.82700, source: "official" },
  { name: "Kurnool-III PS", lat: 15.02450, lng: 78.14450, source: "official" },
  { name: "Ananthapuram PS", lat: 15.15020, lng: 77.42840, source: "official" },
  { name: "Bidar PS", lat: 18.31340, lng: 77.29810, source: "official" },
  { name: "Davanagere/Chitradurga PS", lat: 14.48390, lng: 76.29140, source: "official" },
  { name: "Bellary PS", lat: 15.00560, lng: 76.03080, source: "official" },
  { name: "Bijapur PS", lat: 16.75620, lng: 76.17420, source: "official" },
  { name: "Tumkur-II PS", lat: 14.12680, lng: 77.32750, source: "official" },
  { name: "Ananthapuram-II PS", lat: 14.88400, lng: 76.98290, source: "official" },
  { name: "Bikaner", lat: 28.24920, lng: 73.38190, source: "official" },
  { name: "Fatehgarh PS", lat: 26.85240, lng: 71.50950, source: "official" },
  { name: "Bhadla-II PS", lat: 27.51060, lng: 72.47790, source: "official" },
  { name: "Bikaner-II PS", lat: 28.15560, lng: 73.00650, source: "official" },
  { name: "Fatehgarh-IV PS", lat: 26.25070, lng: 71.23530, source: "official" },
  { name: "Bikaner-IV PS", lat: 28.44530, lng: 73.23750, source: "official" },
  { name: "South Olpad (HVDC)", lat: 21.94600, lng: 73.18261, source: "official" },
  { name: "Ramgarh (HVDC)", lat: 27.47146, lng: 70.59535, source: "official" },
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
