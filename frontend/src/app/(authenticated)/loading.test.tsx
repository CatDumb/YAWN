import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AuthenticatedLoading from "./loading";

describe("AuthenticatedLoading", () => {
  it("keeps loading feedback inside accessible page content", () => {
    render(<AuthenticatedLoading />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});
