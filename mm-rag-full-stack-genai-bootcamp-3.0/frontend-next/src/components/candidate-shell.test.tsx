import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateShell } from "./candidate-shell";

const identity = {
  user: { email: "learner@example.invalid" },
  workspaces: [
    {
      id: "123e4567-e89b-12d3-a456-426614174000",
      name: "Personal workspace",
      role: "owner",
    },
  ],
};

describe("candidate workspace shell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = String(input);
        const body = path.endsWith("users/me") ? identity : [];
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("has no detectable accessibility violations after workspace load", async () => {
    const { container } = render(<CandidateShell />);

    await screen.findByText("Personal workspace · owner");
    await waitFor(() => expect(screen.getByText("No items yet.")).toBeInTheDocument());

    expect(await axe(container)).toHaveNoViolations();
    expect(screen.getByRole("navigation", { name: "Workspace views" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows a non-disclosing failure instead of backend response content", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("private detail", { status: 503 })));

    render(<CandidateShell />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The workspace service is temporarily unavailable.",
    );
    expect(screen.queryByText("private detail")).not.toBeInTheDocument();
  });
});
