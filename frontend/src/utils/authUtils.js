const USER_TYPE_ALIASES = {
  superadmin: "systemadmin",
  "system admin": "systemadmin",
  system_admin: "systemadmin",
  systemadmin: "systemadmin",
  admin: "tenantadmin",
  tenantadmin: "tenantadmin",
  "tenant admin": "tenantadmin",
  tenant_admin: "tenantadmin",
  user: "user",
};

const normalizeUserTypeToken = (value) => {
  if (typeof value !== "string") {
    return "";
  }

  const token = value
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "");
  return USER_TYPE_ALIASES[token] || token;
};

export const getNormalizedEmail = (user) => {
  if (!user?.email) {
    return "";
  }

  return String(user.email).trim().toLowerCase();
};

export const getUserType = (user) => {
  if (!user) {
    return "user";
  }

  const primary = normalizeUserTypeToken(user.user_type);
  if (primary) {
    return primary;
  }

  const fallback = normalizeUserTypeToken(user.role);
  if (fallback) {
    return fallback;
  }

  if (
    user.is_superuser === true ||
    user.is_superuser === "true" ||
    user.isAdmin === true
  ) {
    return "systemadmin";
  }

  const normalizedEmail = getNormalizedEmail(user);
  if (
    normalizedEmail === "systemadmin@autonomy.ai" ||
    normalizedEmail === "superadmin@autonomy.ai"
  ) {
    return "systemadmin";
  }
  if (
    normalizedEmail === "tenantadmin@autonomy.ai"
  ) {
    return "tenantadmin";
  }

  return "user";
};

export const isSystemAdmin = (user) => getUserType(user) === "systemadmin";

export const isTenantAdmin = (user) => {
  const type = getUserType(user);
  if (type === "systemadmin") {
    return true;
  }
  return type === "tenantadmin";
};

export const getDefaultLandingPath = (user) => {
  // Check UI mode preference — Decision Stream is the default for all users
  const uiMode = typeof localStorage !== 'undefined'
    ? localStorage.getItem('ui:mode') || 'stream'
    : 'stream';

  if (isSystemAdmin(user)) {
    return uiMode === 'stream' ? '/decision-stream' : "/system/users";
  }

  if (isTenantAdmin(user)) {
    return uiMode === 'stream' ? '/decision-stream' : "/admin?section=scenarios";
  }

  // For all other users (including USER with Powell capabilities),
  // route based on UI mode preference
  return uiMode === 'stream' ? '/decision-stream' : "/dashboard";
};

const parseRedirectTarget = (target) => {
  if (!target || typeof target !== "string") {
    return null;
  }

  const trimmed = target.trim();
  if (!trimmed || trimmed.includes("://")) {
    return null;
  }

  let path = trimmed;
  let search = "";
  let hash = "";

  const hashIndex = path.indexOf("#");
  if (hashIndex >= 0) {
    hash = path.slice(hashIndex);
    path = path.slice(0, hashIndex);
  }

  const searchIndex = path.indexOf("?");
  if (searchIndex >= 0) {
    search = path.slice(searchIndex);
    path = path.slice(0, searchIndex);
  }

  if (!path) {
    path = "/";
  }

  if (!path.startsWith("/")) {
    path = `/${path}`;
  }

  if (path.startsWith("//")) {
    return null;
  }

  const normalizedPath = path.length > 1 ? path.replace(/\/+$/, "") : path;

  return {
    pathname: normalizedPath,
    fullPath: `${normalizedPath}${search}${hash}`,
  };
};

export const resolvePostLoginDestination = (user, redirectTo) => {
  const fallback = getDefaultLandingPath(user);
  if (!redirectTo) {
    return fallback;
  }

  const parsed = parseRedirectTarget(redirectTo);
  if (!parsed) {
    return fallback;
  }

  if (isSystemAdmin(user)) {
    const blockedPaths = [
      '/',
      '/dashboard',
    ];

    if (blockedPaths.includes(parsed.pathname) || parsed.pathname.startsWith('/admin')) {
      return fallback;
    }
  }

  return parsed.fullPath;
};

/**
 * Builds the appropriate login URL for redirecting an unauthenticated user.
 * Avoids appending a redirect back to the root route (`/`) so that the
 * application doesn't appear to "recycle" to `/login?redirect=%2F` on first
 * load. Accepts either a React Router location object or a path string.
 */
export const buildLoginRedirectPath = (locationLike) => {
  if (!locationLike) {
    return "/login";
  }

  let pathname = "/";
  let search = "";

  if (typeof locationLike === "string") {
    const withoutHash = locationLike.split("#")[0] || "/";
    const [pathPart, searchPart] = withoutHash.split("?");
    pathname = pathPart.startsWith("/") ? pathPart : `/${pathPart}`;
    search = searchPart ? `?${searchPart}` : "";
  } else {
    pathname = locationLike.pathname || "/";
    search = locationLike.search || "";
  }

  pathname = pathname.startsWith("/") ? pathname : `/${pathname}`;

  const shouldIncludeRedirect = !(pathname === "/" && !search);

  if (!shouldIncludeRedirect) {
    return "/login";
  }

  const target = `${pathname}${search}`;
  return `/login?redirect=${encodeURIComponent(target)}`;
};
