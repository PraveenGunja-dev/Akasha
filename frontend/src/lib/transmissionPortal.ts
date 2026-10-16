/* The transmission portal (Unada), opened from the Transmission screens.

   Each project opens its own executive dashboard, signed in:
     {portal}/transmission/v1/dashboard/{khavda|rajasthan}/executive?project={id}/#lt={token}

   The portal address and the login token are set per server in frontend/.env
   (not committed), so no credential lands in git:
     VITE_TRANSMISSION_PORTAL_URL=https://adani-transmission-testing.unada.in
     VITE_TRANSMISSION_PORTAL_TOKEN=<the #lt= token>
   They are fixed into the build: set them before `npm run build`. Without a
   token the portal's own login page opens. */
const RAW: string = import.meta.env.VITE_TRANSMISSION_PORTAL_URL || 'https://adani-transmission-testing.unada.in';

// A full sign-in link pasted into the URL variable also works: its #lt= is used.
const TOKEN: string = import.meta.env.VITE_TRANSMISSION_PORTAL_TOKEN || (RAW.match(/#lt=([^&]+)/)?.[1] ?? '');

const BASE: string = (() => {
  try {
    return new URL(RAW).origin;
  } catch {
    return 'https://adani-transmission-testing.unada.in';
  }
})();

/** The portal link for one project (its P6 project id, e.g. FY26-P01), in the
 *  region its cluster belongs to; without a project, the region dashboard. */
export function transmissionPortalLink(o: { projectId?: string | null; cluster?: string | null; region?: string | null } = {}): string {
  const region = /rajasthan/i.test(`${o.region ?? ''} ${o.cluster ?? ''}`) ? 'rajasthan' : 'khavda';
  const query = o.projectId ? `?project=${encodeURIComponent(o.projectId)}/` : '';
  return `${BASE}/transmission/v1/dashboard/${region}/executive${query}${TOKEN ? `#lt=${TOKEN}` : ''}`;
}

export const TRANSMISSION_PORTAL_URL: string = transmissionPortalLink();
