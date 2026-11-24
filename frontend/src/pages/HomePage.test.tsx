import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HomePage } from "./HomePage";

describe("HomePage", () => {
  it("renders the app title", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "GTM Launch Studio" }),
    ).toBeInTheDocument();
  });

  it("renders the placeholder card", () => {
    render(<HomePage />);
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });
});
