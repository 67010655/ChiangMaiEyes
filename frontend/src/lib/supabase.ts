import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

// Alerts are an optional feature: if Supabase isn't configured (e.g. local dev
// without keys), `supabase` is null and the UI hides the subscribe controls.
export const supabase = url && anonKey ? createClient(url, anonKey) : null;

export type AlertSubscription = {
  id: string;
  location_name: string;
  latitude: number;
  longitude: number;
  radius_km: number;
  is_active: boolean;
  created_at: string;
};
