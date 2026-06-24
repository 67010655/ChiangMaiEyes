import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceModeChip } from "./SourceModeChip";

describe("SourceModeChip", () => {
  it("renders prototype label honestly", () => {
    const html = renderToStaticMarkup(<SourceModeChip mode="PROTOTYPE" />);

    expect(html).toContain("ข้อมูลต้นแบบ");
    expect(html).toContain("source-mode-chip--prototype");
  });

  it("renders live label", () => {
    const html = renderToStaticMarkup(<SourceModeChip mode="LIVE" />);

    expect(html).toContain("สด");
    expect(html).toContain("source-mode-chip--live");
  });
});
