/** Minimal class joiner. No new dependency — clsx/tailwind-merge are not in the
 *  bundle and this system never needs conflict resolution, only concatenation. */
export const cx = (...parts: Array<string | false | null | undefined>): string =>
  parts.filter(Boolean).join(' ');
