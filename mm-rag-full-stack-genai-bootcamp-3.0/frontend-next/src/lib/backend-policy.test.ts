import { describe, expect, it } from "vitest";

import { hasTrustedMutationOrigin, isAllowedBackendRoute } from "./backend-policy";

const workspace = "123e4567-e89b-12d3-a456-426614174000";

describe("backend boundary", () => {
  it("allows only reviewed routes and methods", () => {
    expect(isAllowedBackendRoute("GET", "/api/v1/users/me")).toBe(true);
    expect(isAllowedBackendRoute("GET", `/api/v1/workspaces/${workspace}/documents`)).toBe(true);
    expect(isAllowedBackendRoute("DELETE", `/api/v1/workspaces/${workspace}/documents`)).toBe(false);
    expect(isAllowedBackendRoute("GET", "/api/v1/admin/secrets")).toBe(false);
    expect(isAllowedBackendRoute("GET", "/api/v1/users/me/../admin")).toBe(false);
    expect(isAllowedBackendRoute("GET", "/api/v1/workspaces/not-a-uuid/documents")).toBe(false);
    expect(isAllowedBackendRoute("GET", `/api/v1/workspaces/${workspace}/documents/extra`)).toBe(false);
  });

  it("requires an exact same-origin mutation", () => {
    expect(hasTrustedMutationOrigin("https://rag.example/api/backend/x", "https://rag.example")).toBe(true);
    expect(hasTrustedMutationOrigin("https://rag.example/api/backend/x", "https://evil.example")).toBe(false);
    expect(hasTrustedMutationOrigin("https://rag.example/api/backend/x", null)).toBe(false);
    expect(hasTrustedMutationOrigin("https://rag.example/api/backend/x", "https://rag.example:444")).toBe(false);
  });
});
