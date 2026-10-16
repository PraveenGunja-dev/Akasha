/* The transmission portal (Unada), opened from the Transmission screens.

   The sign-in link - the portal address with its #lt= login token - is set
   per server in VITE_TRANSMISSION_PORTAL_URL (frontend/.env, not committed),
   so no credential lands in git. It is fixed into the build: set it before
   `npm run build`. Without it the portal's own login page opens. */
export const TRANSMISSION_PORTAL_URL: string =
  import.meta.env.VITE_TRANSMISSION_PORTAL_URL || 'https://adani-transmission-testing.unada.in';
