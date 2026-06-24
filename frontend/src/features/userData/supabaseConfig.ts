export type SupabaseConfig = {
  url: string;
  publishableKey: string;
};

type SupabaseEnv = {
  VITE_SUPABASE_URL?: string;
  VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  VITE_SUPABASE_ANON_KEY?: string;
};

export type FieldReportInput = {
  userId: string;
  forestId: string;
  patrolCount?: number;
  firebreakKm?: number;
  fuelManagementRai?: number;
  latitude?: number | null;
  longitude?: number | null;
  note?: string;
};

export type SavedLocationInput = {
  userId: string;
  label: string;
  latitude: number;
  longitude: number;
};

export function getSupabaseConfig(
  env: SupabaseEnv = import.meta.env as SupabaseEnv,
): SupabaseConfig {
  return {
    url: env.VITE_SUPABASE_URL?.trim() ?? "",
    publishableKey:
      env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() ??
      env.VITE_SUPABASE_ANON_KEY?.trim() ??
      "",
  };
}

export function isSupabaseConfigured(config = getSupabaseConfig()) {
  return Boolean(config.url && config.publishableKey);
}

export function buildFieldReportInsert(input: FieldReportInput) {
  return {
    user_id: input.userId,
    forest_id: input.forestId,
    report_type: "weekly_activity",
    patrol_count: input.patrolCount ?? 0,
    firebreak_km: input.firebreakKm ?? 0,
    fuel_management_rai: input.fuelManagementRai ?? 0,
    latitude: input.latitude ?? null,
    longitude: input.longitude ?? null,
    note: input.note?.trim() ?? "",
    verification_status: "pending",
  };
}

export function buildSavedLocationInsert(input: SavedLocationInput) {
  return {
    user_id: input.userId,
    label: input.label.trim(),
    latitude: input.latitude,
    longitude: input.longitude,
  };
}
