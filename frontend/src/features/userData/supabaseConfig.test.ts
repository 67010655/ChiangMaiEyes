import { describe, expect, it } from "vitest";

import {
  buildFieldReportInsert,
  buildSavedLocationInsert,
  getSupabaseConfig,
  isSupabaseConfigured,
} from "./supabaseConfig";

describe("supabaseConfig", () => {
  it("requires both url and publishable key", () => {
    expect(isSupabaseConfigured({ url: "", publishableKey: "key" })).toBe(false);
    expect(isSupabaseConfigured({ url: "https://example.supabase.co", publishableKey: "" })).toBe(false);
    expect(
      isSupabaseConfigured({
        url: "https://example.supabase.co",
        publishableKey: "sb_publishable_test",
      }),
    ).toBe(true);
  });

  it("reads Vite environment values", () => {
    const config = getSupabaseConfig({
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
    });

    expect(config).toEqual({
      url: "https://example.supabase.co",
      publishableKey: "sb_publishable_test",
    });
  });

  it("supports legacy anon key env for existing deployments", () => {
    const config = getSupabaseConfig({
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_SUPABASE_ANON_KEY: "legacy_anon_key",
    });

    expect(config.publishableKey).toBe("legacy_anon_key");
  });

  it("builds safe field report insert payloads", () => {
    expect(
      buildFieldReportInsert({
        userId: "user-1",
        forestId: "cf-1",
        patrolCount: 2,
        firebreakKm: 1.5,
        fuelManagementRai: 10,
        latitude: 18.5,
        longitude: 98.3,
        note: "checked firebreak",
      }),
    ).toMatchObject({
      user_id: "user-1",
      forest_id: "cf-1",
      report_type: "weekly_activity",
      patrol_count: 2,
      firebreak_km: 1.5,
      fuel_management_rai: 10,
      latitude: 18.5,
      longitude: 98.3,
      note: "checked firebreak",
      verification_status: "pending",
    });
  });

  it("builds saved location insert payloads", () => {
    expect(
      buildSavedLocationInsert({
        userId: "user-1",
        label: "Mae Chaem Community Forest",
        latitude: 18.5,
        longitude: 98.3,
      }),
    ).toEqual({
      user_id: "user-1",
      label: "Mae Chaem Community Forest",
      latitude: 18.5,
      longitude: 98.3,
    });
  });
});
