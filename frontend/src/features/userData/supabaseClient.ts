import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseConfig, isSupabaseConfigured } from "./supabaseConfig";

let client: SupabaseClient | null = null;

export function getSupabaseClient() {
  const config = getSupabaseConfig();
  if (!isSupabaseConfigured(config)) return null;
  if (!client) {
    client = createClient(config.url, config.publishableKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    });
  }
  return client;
}
