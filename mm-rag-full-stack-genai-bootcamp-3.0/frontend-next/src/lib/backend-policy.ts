const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const READ_PATHS = [
  /^\/api\/v1\/users\/me$/,
  /^\/api\/v1\/health\/ready$/,
  new RegExp(`^/api/v1/workspaces/${UUID}/(documents|collections|conversations|activity|feedback)$`),
  new RegExp(`^/api/v1/workspaces/${UUID}/ingestion/jobs$`),
  new RegExp(`^/api/v1/workspaces/${UUID}/conversations/${UUID}$`),
];
const WRITE_PATHS = [
  new RegExp(`^/api/v1/workspaces/${UUID}/conversations$`),
  new RegExp(`^/api/v1/workspaces/${UUID}/conversations/${UUID}/messages$`),
  new RegExp(`^/api/v1/workspaces/${UUID}/feedback/conversations/${UUID}/messages/${UUID}$`),
];

export function isAllowedBackendRoute(method: string, path: string): boolean {
  const patterns = method === "GET" ? READ_PATHS : method === "POST" ? WRITE_PATHS : [];
  return patterns.some((pattern) => pattern.test(path));
}

export function hasTrustedMutationOrigin(expectedBaseUrl: string, origin: string | null): boolean {
  if (!origin) return false;
  try {
    const expectedOrigin = new URL(expectedBaseUrl).origin;
    const suppliedOrigin = new URL(origin);
    // Browser Origin headers contain only the serialized origin, never a path or user info.
    return origin === suppliedOrigin.origin && expectedOrigin === suppliedOrigin.origin;
  } catch {
    return false;
  }
}
