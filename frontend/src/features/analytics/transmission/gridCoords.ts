// Approximate town/substation-area coordinates for portfolio-level visualization.
// Matching is done by substring against the real substation labels coming from the
// TC network tables (e.g. "Bhadla-III", "Kps-II (HVDC)" both resolve to their base entry).
// A handful of real substation names have no confident public coordinate (small villages /
// generic labels) and are intentionally left unmapped rather than guessed — see
// UNMATCHED note in TransmissionDataViewer.

export interface SubstationCoord {
  name: string;
  lat: number;
  lng: number;
}

export const SUBSTATION_COORDS: SubstationCoord[] = [
  { name: "Padghe", lat: 19.353, lng: 73.212 },
  { name: "Pirana", lat: 22.872, lng: 72.557 },
  { name: "South Olpad", lat: 21.890, lng: 73.086 },
  { name: "Lakadia", lat: 23.394, lng: 70.598 },
  { name: "Halvad", lat: 22.911, lng: 71.231 },
  { name: "Boisar", lat: 19.742, lng: 72.785 },
  { name: "Khavda", lat: 24.024, lng: 69.337 },
  { name: "Kps", lat: 24.024, lng: 69.337 },
  { name: "Bhuj", lat: 23.379, lng: 69.592 },
  { name: "Pune", lat: 18.734, lng: 73.699 },
  { name: "Banaskantha", lat: 24.090, lng: 72.000 },
  { name: "Ramgarh", lat: 27.471, lng: 70.494 },
  { name: "Bhadla", lat: 27.618, lng: 72.206 },
  { name: "Fatehgarh", lat: 26.285, lng: 71.100 },
  { name: "Sikar", lat: 27.612, lng: 75.088 },
  { name: "Khetri", lat: 27.951, lng: 75.709 },
  { name: "Narela", lat: 28.753, lng: 76.984 },
  { name: "Jhatikara", lat: 28.462, lng: 76.937 },
  { name: "Bikaner", lat: 28.373, lng: 73.171 },
  { name: "Mandsaur", lat: 24.207, lng: 75.171 },
  { name: "Indore", lat: 22.909, lng: 75.900 },
  { name: "Mandvi", lat: 22.833, lng: 69.355 },
  { name: "Ahmedabad", lat: 23.0225, lng: 72.5714 },
  { name: "Bhopal", lat: 23.2599, lng: 77.4126 },
  { name: "Dwarka", lat: 22.2394, lng: 68.9678 },
  { name: "Hazira", lat: 21.1167, lng: 72.6500 },
  { name: "Hinjewadi", lat: 18.5913, lng: 73.7389 },
  { name: "Kanpur", lat: 26.4499, lng: 80.3319 },
  { name: "Nagpur", lat: 21.1458, lng: 79.0882 },
  { name: "Navsari", lat: 20.9467, lng: 72.9520 },
  { name: "Raipur", lat: 21.2514, lng: 81.6296 },
  { name: "Vadodara", lat: 22.3072, lng: 73.1812 },
  { name: "Varanasi", lat: 25.3176, lng: 82.9739 },
  { name: "Beawar", lat: 26.1004, lng: 74.3197 },
  { name: "Fatehpur", lat: 27.9926, lng: 74.9455 },
  { name: "Koyna", lat: 17.4022, lng: 73.7503 },
  { name: "Ghandhar", lat: 21.9333, lng: 72.8333 },
];

// Longest name first so a more specific entry (if one is ever added) wins over a shorter
// generic prefix match.
const SORTED_COORDS = [...SUBSTATION_COORDS].sort((a, b) => b.name.length - a.name.length);

export function findSubstationCoord(label?: string | null): SubstationCoord | null {
  if (!label) return null;
  const norm = label.toLowerCase();
  for (const sub of SORTED_COORDS) {
    if (norm.includes(sub.name.toLowerCase())) return sub;
  }
  return null;
}
