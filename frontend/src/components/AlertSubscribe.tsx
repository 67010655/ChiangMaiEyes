import { useCallback, useEffect, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import { Bell, BellOff, LogOut, Mail, Trash2 } from 'lucide-react';
import { supabase, type AlertSubscription } from '../lib/supabase';

type Props = {
  /** The currently pinned [lat, lon], if any. */
  pinnedLocation: [number, number] | null;
};

const RADIUS_OPTIONS = [10, 25, 50] as const;

export function AlertSubscribe({ pinnedLocation }: Props) {
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState('');
  const [linkSent, setLinkSent] = useState(false);
  const [subscriptions, setSubscriptions] = useState<AlertSubscription[]>([]);
  const [radiusKm, setRadiusKm] = useState<number>(25);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => listener.subscription.unsubscribe();
  }, []);

  const loadSubscriptions = useCallback(() => {
    if (!supabase || !session) return;
    supabase
      .from('alert_subscriptions')
      .select('id, location_name, latitude, longitude, radius_km, is_active, created_at')
      .order('created_at', { ascending: false })
      .then(({ data }) => setSubscriptions((data as AlertSubscription[]) ?? []));
  }, [session]);

  useEffect(() => {
    loadSubscriptions();
  }, [loadSubscriptions]);

  if (!supabase) return null;
  const sb = supabase; // narrowed to non-null for the closures below

  const sendMagicLink = async () => {
    if (!email.trim()) return;
    setBusy(true);
    setMessage(null);
    const { error } = await sb.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    setBusy(false);
    if (error) {
      setMessage(`ส่งลิงก์ไม่สำเร็จ: ${error.message}`);
    } else {
      setLinkSent(true);
      setMessage('ส่งลิงก์เข้าสู่ระบบไปที่อีเมลแล้ว — เปิดอีเมลแล้วคลิกลิงก์เพื่อเข้าสู่ระบบ');
    }
  };

  const signOut = async () => {
    await sb.auth.signOut();
    setSubscriptions([]);
    setLinkSent(false);
  };

  const subscribeHere = async () => {
    if (!pinnedLocation || !session) return;
    setBusy(true);
    setMessage(null);
    const { error } = await sb.from('alert_subscriptions').insert({
      user_id: session.user.id,
      email: session.user.email,
      location_name: `พิกัด ${pinnedLocation[0].toFixed(3)}, ${pinnedLocation[1].toFixed(3)}`,
      latitude: pinnedLocation[0],
      longitude: pinnedLocation[1],
      radius_km: radiusKm,
    });
    setBusy(false);
    if (error) {
      setMessage(`บันทึกไม่สำเร็จ: ${error.message}`);
    } else {
      setMessage(`ตั้งแจ้งเตือนแล้ว — จะอีเมลแจ้งเมื่อมีจุดความร้อนใหม่ในรัศมี ${radiusKm} กม.`);
      loadSubscriptions();
    }
  };

  const removeSubscription = async (id: string) => {
    setBusy(true);
    await sb.from('alert_subscriptions').delete().eq('id', id);
    setBusy(false);
    loadSubscriptions();
  };

  // ── Logged out: ask for email, send magic link ──
  if (!session) {
    return (
      <div className="alert-subscribe card">
        <span className="card__title"><Bell size={15} /> แจ้งเตือนทางอีเมลเมื่อมีจุดความร้อนใกล้บ้าน</span>
        {linkSent ? (
          <p className="alert-subscribe__message">{message}</p>
        ) : (
          <div className="alert-subscribe__form">
            <div className="alert-subscribe__email">
              <Mail size={15} />
              <input
                type="email"
                placeholder="อีเมลของคุณ"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <button type="button" className="btn-primary" onClick={sendMagicLink} disabled={busy || !email.trim()}>
              ส่งลิงก์เข้าสู่ระบบ
            </button>
          </div>
        )}
        {message && !linkSent && <p className="alert-subscribe__message alert-subscribe__message--error">{message}</p>}
        <small className="card__foot">ไม่ต้องตั้งรหัสผ่าน — แค่คลิกลิงก์ในอีเมลเพื่อเข้าสู่ระบบ</small>
      </div>
    );
  }

  // ── Logged in: manage subscriptions ──
  return (
    <div className="alert-subscribe card">
      <div className="alert-subscribe__header">
        <span className="card__title"><Bell size={15} /> แจ้งเตือนทางอีเมล</span>
        <button type="button" className="btn-clear" onClick={signOut}>
          <LogOut size={13} /> ออกจากระบบ
        </button>
      </div>
      <p className="alert-subscribe__email-display">{session.user.email}</p>

      {pinnedLocation ? (
        <div className="alert-subscribe__form">
          <label className="alert-subscribe__radius-label">
            แจ้งเตือนเมื่อมีจุดความร้อนในรัศมี:
            <select value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))}>
              {RADIUS_OPTIONS.map((r) => (
                <option key={r} value={r}>{r} กม.</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn-primary" onClick={subscribeHere} disabled={busy}>
            <Bell size={14} /> ตั้งแจ้งเตือนสำหรับพิกัดนี้
          </button>
        </div>
      ) : (
        <p className="alert-subscribe__hint">💡 ปักหมุดตำแหน่งบนแผนที่ก่อน แล้วกลับมาตั้งแจ้งเตือนได้เลย</p>
      )}

      {message && <p className="alert-subscribe__message">{message}</p>}

      {subscriptions.length > 0 && (
        <ul className="alert-subscribe__list">
          {subscriptions.map((sub) => (
            <li key={sub.id}>
              <BellOff size={13} className="alert-subscribe__list-icon" />
              <span>{sub.location_name} · รัศมี {sub.radius_km} กม.</span>
              <button type="button" className="btn-clear" onClick={() => removeSubscription(sub.id)} aria-label="ลบการแจ้งเตือน">
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
