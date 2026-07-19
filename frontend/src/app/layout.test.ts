import { isValidElement } from "react";
import { describe, expect, it } from "vitest";

import RootLayout, { metadata } from "./layout";

describe("RootLayout", () => {
  it("sets app metadata and renders supplied content", () => {
    const layout = RootLayout({ children: "Dashboard" });

    expect(metadata.title).toBe("WIO Tracker");
    expect(isValidElement(layout)).toBe(true);
    expect(layout.props.lang).toBe("en");
  });
});
