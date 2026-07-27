export type DevelopmentRole = 'executive' | 'pmag';

const DEV_USER_KEY = 'akasha_dev_user';
const DEV_ROLE_KEY = 'akasha_dev_role';
const DEV_PROFILE_PREFIX = 'akasha_dev_profile_v1_';
const VALID_USER_ID = /^[A-Za-z0-9-]{8,64}$/;

function profileKey(role: DevelopmentRole): string {
  return `${DEV_PROFILE_PREFIX}${role}`;
}

function validRole(value: string | null): value is DevelopmentRole {
  return value === 'executive' || value === 'pmag';
}

function validUserId(value: string | null): value is string {
  return Boolean(value && VALID_USER_ID.test(value));
}

export function getDevelopmentIdentity(): { userId: string; role: DevelopmentRole } | null {
  const userId = sessionStorage.getItem(DEV_USER_KEY);
  const role = sessionStorage.getItem(DEV_ROLE_KEY);
  if (!validUserId(userId) || !validRole(role)) return null;

  // Preserve identities created by older builds before logout can discard the session value.
  localStorage.setItem(profileKey(role), userId);
  return { userId, role };
}

export function startDevelopmentSession(
  role: DevelopmentRole,
  createId: () => string = () => crypto.randomUUID(),
): { userId: string; role: DevelopmentRole } {
  const storedProfile = localStorage.getItem(profileKey(role));
  const userId = validUserId(storedProfile) ? storedProfile : createId();
  if (!validUserId(userId)) throw new Error('Unable to create a valid development identity.');

  localStorage.setItem(profileKey(role), userId);
  sessionStorage.setItem(DEV_USER_KEY, userId);
  sessionStorage.setItem(DEV_ROLE_KEY, role);
  return { userId, role };
}

export function clearDevelopmentSession(): void {
  sessionStorage.removeItem(DEV_USER_KEY);
  sessionStorage.removeItem(DEV_ROLE_KEY);
}
