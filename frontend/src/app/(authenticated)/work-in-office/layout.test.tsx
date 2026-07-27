import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import WorkInOfficeLayout from "./layout";

describe("WorkInOfficeLayout", () => {
  afterEach(cleanup);

  it("leaves route protection to shared AppShell", () => {
    render(
      <WorkInOfficeLayout>
        <p>Private WIO</p>
      </WorkInOfficeLayout>,
    );
    expect(screen.getByText("Private WIO")).toBeInTheDocument();
  });
});
