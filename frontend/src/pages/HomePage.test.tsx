import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

const fetchMock = vi.hoisted(() => vi.fn<(request: Request) => Promise<Response>>());

// Swap the shared client's network for a mock but keep the real client, middleware and types.
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    api: actual.createApiClient({ baseUrl: "http://localhost", fetch: fetchMock }),
  };
});

function renderHome() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <HomePage />
    </QueryClientProvider>,
  );
}

describe("HomePage", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(Response.json({ status: "ok", version: "0.1.0", env: "test" }));
  });

  it("renders the app title", () => {
    renderHome();
    expect(
      screen.getByRole("heading", { level: 1, name: "GTM Launch Studio" }),
    ).toBeInTheDocument();
  });

  it("renders the placeholder card", () => {
    renderHome();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("shows API: ok once the health check succeeds", async () => {
    renderHome();
    expect(screen.getByRole("status")).toHaveTextContent("API: checking");
    expect(await screen.findByText("API: ok")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0].url).toBe("http://localhost/api/health");
  });

  it("shows API: unreachable when the request fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderHome();
    expect(await screen.findByText("API: unreachable")).toBeInTheDocument();
  });

  it("shows API: unreachable when the API answers with an error", async () => {
    fetchMock.mockResolvedValue(Response.json({ detail: "down" }, { status: 503 }));
    renderHome();
    expect(await screen.findByText("API: unreachable")).toBeInTheDocument();
  });
});
