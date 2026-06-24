import { useMemo, useState } from "react";
import { Send, UserRound } from "lucide-react";

import {
  buildFieldReportInsert,
  buildSavedLocationInsert,
  isSupabaseConfigured,
} from "./supabaseConfig";
import { getSupabaseClient } from "./supabaseClient";

type Props = {
  forestId: string | null;
  forestName: string | null;
  latitude?: number | null;
  longitude?: number | null;
  configured?: boolean;
};

export function UserDataPanel({
  forestId,
  forestName,
  latitude = null,
  longitude = null,
  configured = isSupabaseConfigured(),
}: Props) {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");
  const canSubmit = configured && Boolean(forestId);
  const canSaveLocation = configured && Boolean(forestName) && latitude !== null && longitude !== null;
  const selectedForest = forestName || "ยังไม่ได้เลือกป่าชุมชน";
  const setupText = useMemo(
    () =>
      "ต้องตั้งค่า VITE_SUPABASE_URL และ VITE_SUPABASE_PUBLISHABLE_KEY เพื่อเปิดบัญชีผู้ใช้ การบันทึกตำแหน่ง และรายงานภาคสนาม",
    [],
  );

  async function requestMagicLink() {
    const supabase = getSupabaseClient();
    if (!supabase || !email.trim()) return;
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    setStatus(error ? error.message : "ส่งลิงก์เข้าสู่ระบบไปที่อีเมลแล้ว");
  }

  async function submitReport() {
    const supabase = getSupabaseClient();
    if (!supabase || !forestId) return;
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();
    if (userError || !user) {
      setStatus("กรุณาเข้าสู่ระบบก่อนส่งรายงานภาคสนาม");
      return;
    }
    const payload = buildFieldReportInsert({
      userId: user.id,
      forestId,
      note,
    });
    const { error } = await supabase.from("field_reports").insert(payload);
    setStatus(error ? error.message : "บันทึกรายงานแล้ว รอตรวจสอบก่อนเข้าคะแนนรายสัปดาห์");
    if (!error) setNote("");
  }

  async function saveLocation() {
    const supabase = getSupabaseClient();
    if (!supabase || !forestName || latitude === null || longitude === null) return;
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();
    if (userError || !user) {
      setStatus("กรุณาเข้าสู่ระบบก่อนบันทึกตำแหน่ง");
      return;
    }
    const payload = buildSavedLocationInsert({
      userId: user.id,
      label: forestName,
      latitude,
      longitude,
    });
    const { error } = await supabase.from("user_saved_locations").insert(payload);
    setStatus(error ? error.message : "บันทึกตำแหน่งแล้ว");
  }

  return (
    <section className="user-data-panel">
      <div className="user-data-panel__head">
        <span className="user-data-panel__icon">
          <UserRound size={18} />
        </span>
        <div>
          <span>บัญชีและรายงานภาคสนาม</span>
          <strong>{selectedForest}</strong>
        </div>
      </div>

      {!configured && (
        <p className="user-data-panel__setup">
          ยังไม่ได้เปิดระบบบันทึกข้อมูลจริง {setupText}
        </p>
      )}

      <div className="user-data-panel__form">
        <label>
          <span>อีเมลผู้รายงาน</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="reporter@example.com"
            disabled={!configured}
          />
        </label>
        <button type="button" onClick={requestMagicLink} disabled={!configured || !email.trim()}>
          ส่งลิงก์เข้าสู่ระบบ
        </button>
      </div>

      <button type="button" onClick={saveLocation} disabled={!canSaveLocation}>
        บันทึกตำแหน่งป่าชุมชนนี้
      </button>

      <label className="user-data-panel__report">
        <span>รายงานกิจกรรมป่าชุมชน</span>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="เช่น ลาดตระเวน ทำแนวกันไฟ จัดการเชื้อเพลิง แหล่งน้ำ หรือข้อตกลงห้ามเผา"
          disabled={!canSubmit}
        />
      </label>
      <button
        type="button"
        className="user-data-panel__submit"
        onClick={submitReport}
        disabled={!canSubmit || !note.trim()}
      >
        <Send size={14} />
        ส่งรายงานกิจกรรม
      </button>
      {status && <p className="user-data-panel__status">{status}</p>}
    </section>
  );
}
