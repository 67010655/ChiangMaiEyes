import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { UserDataPanel } from "./UserDataPanel";

describe("UserDataPanel", () => {
  it("renders a setup state when Supabase is not configured", () => {
    const html = renderToStaticMarkup(
      <UserDataPanel forestId="cf-1" forestName="Mae Chaem" configured={false} />,
    );

    expect(html).toContain("VITE_SUPABASE_URL");
    expect(html).toContain("รายงานภาคสนาม");
    expect(html).toContain("บันทึกตำแหน่งป่าชุมชนนี้");
  });
});
