import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageCircle, Send, Sparkles, X } from 'lucide-react';
import type { DashboardResponse } from '../lib/types';
import { chatWithAdvisor, generateDailyBriefing, GROQ_KEY_VALID, type ChatMessage } from '../lib/gemini';

type Props = {
  dashboard: DashboardResponse;
};

export function AiAdvisor({ dashboard }: Props) {
  const [briefing, setBriefing] = useState<string | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [quotaError, setQuotaError] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Generate daily briefing on mount / data change
  useEffect(() => {
    let cancelled = false;
    setBriefingLoading(true);
    generateDailyBriefing(dashboard)
      .then((text) => {
        if (!cancelled) setBriefing(text);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          if (err.message === 'QUOTA_EXCEEDED') setQuotaError(true);
          setBriefing(null);
        }
      })
      .finally(() => {
        if (!cancelled) setBriefingLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dashboard]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input when chat opens
  useEffect(() => {
    if (chatOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [chatOpen]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatMessage = { role: 'user', text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      const reply = await chatWithAdvisor(dashboard, messages, text);
      setMessages((prev) => [...prev, { role: 'model', text: reply }]);
    } catch (err) {
      const isQuota = err instanceof Error && err.message === 'QUOTA_EXCEEDED';
      setMessages((prev) => [
        ...prev,
        {
          role: 'model',
          text: isQuota
            ? '⚠️ Groq quota หมดชั่วคราว — กรุณารอสักครู่หรือสร้าง Groq API key ใหม่จาก console.groq.com'
            : `ขออภัย เกิดข้อผิดพลาด: ${err instanceof Error ? err.message : 'ไม่ทราบสาเหตุ'}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, dashboard, messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const quickQuestions = [
    'วันนี้ไปเที่ยวไหนดี?',
    'มีไฟป่าตรงไหนบ้าง?',
    'สถานการณ์ฝุ่นเป็นยังไง?',
    'แนะนำร้านกาแฟดอยสุเทพ',
  ];

  return (
    <>
      {/* ── Daily briefing card (replaces old static advice summary) ── */}
      <div className="ai-briefing">
        <div className="ai-briefing__header">
          <Sparkles size={16} className="ai-briefing__icon" />
          <span className="ai-briefing__title">สรุปสถานการณ์วันนี้ โดยคุณเชียงใหม่</span>
        </div>
        {!GROQ_KEY_VALID ? (
          <div className="ai-briefing__text ai-briefing__text--fallback">
            ยังไม่ได้ตั้งค่า API key —{' '}
            <a href="https://console.groq.com/keys" target="_blank" rel="noopener" className="ai-briefing__setup-link">
              ขอ Groq API key ฟรีที่นี่
            </a>{' '}
            แล้วใส่ใน <code>frontend/.env</code>
            <br /><small style={{ opacity: 0.7 }}>รูปแบบ: VITE_GROQ_API_KEY=gsk_...</small>
          </div>
        ) : briefingLoading ? (
          <div className="ai-briefing__loading">
            <span className="ai-dot-pulse" />
            <span>กำลังวิเคราะห์ข้อมูล...</span>
          </div>
        ) : briefing ? (
          <div className="ai-briefing__text">{briefing}</div>
        ) : quotaError ? (
          <div className="ai-briefing__text ai-briefing__text--fallback">
            ⚠️ Groq quota หมดชั่วคราว — กรุณารอสักครู่หรือ{' '}
            <a href="https://console.groq.com/keys" target="_blank" rel="noopener" className="ai-briefing__setup-link">
              สร้าง Groq key ใหม่
            </a>{' '}
            จาก console.groq.com
          </div>
        ) : (
          <div className="ai-briefing__text ai-briefing__text--fallback">
            ไม่สามารถดึงข้อมูล AI ได้ในขณะนี้
          </div>
        )}
        <button
          type="button"
          className="ai-briefing__chat-btn"
          onClick={() => setChatOpen(true)}
          aria-label="เปิดแชทกับคุณเชียงใหม่"
        >
          <MessageCircle size={14} />
          ถามคุณเชียงใหม่
        </button>
      </div>

      {/* ── Chat panel (slide-up from bottom) ── */}
      {chatOpen && (
        <div className="ai-chat-overlay" onClick={() => setChatOpen(false)}>
          <div className="ai-chat" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="ai-chat__header">
              <div className="ai-chat__header-left">
                <Sparkles size={16} />
                <span>คุณเชียงใหม่</span>
              </div>
              <button type="button" className="ai-chat__close" onClick={() => setChatOpen(false)} aria-label="ปิดแชท">
                <X size={18} />
              </button>
            </div>

            {/* Messages */}
            <div className="ai-chat__messages" ref={scrollRef}>
              {/* Welcome message */}
              <div className="ai-chat__msg ai-chat__msg--model">
                <span className="ai-chat__msg-text">
                  สวัสดีครับ! ผม "คุณเชียงใหม่" ผู้เชี่ยวชาญด้านหมอกควันและไกด์ท่องเที่ยวประจำจังหวัดเชียงใหม่ ถามอะไรเกี่ยวกับสถานการณ์ฝุ่น จุดความร้อน หรือสถานที่ท่องเที่ยวได้เลยครับ 🌿
                </span>
              </div>

              {messages.map((msg, i) => (
                <div key={i} className={`ai-chat__msg ai-chat__msg--${msg.role}`}>
                  <span className="ai-chat__msg-text">{msg.text}</span>
                </div>
              ))}

              {sending && (
                <div className="ai-chat__msg ai-chat__msg--model">
                  <span className="ai-chat__msg-text">
                    <span className="ai-dot-pulse" />
                  </span>
                </div>
              )}
            </div>

            {/* Quick questions (show only when no messages yet) */}
            {messages.length === 0 && (
              <div className="ai-chat__quick">
                {quickQuestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="ai-chat__quick-btn"
                    onClick={() => {
                      setInput(q);
                      // Auto-send after a tick
                      setTimeout(() => {
                        const userMsg: ChatMessage = { role: 'user', text: q };
                        setMessages([userMsg]);
                        setSending(true);
                        chatWithAdvisor(dashboard, [], q)
                          .then((reply) => setMessages((prev) => [...prev, { role: 'model', text: reply }]))
                          .catch((err) =>
                            setMessages((prev) => [
                              ...prev,
                              { role: 'model', text: `ขออภัย: ${err instanceof Error ? err.message : 'ข้อผิดพลาด'}` },
                            ]),
                          )
                          .finally(() => setSending(false));
                        setInput('');
                      }, 50);
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {/* Input */}
            <div className="ai-chat__input-bar">
              <input
                ref={inputRef}
                type="text"
                className="ai-chat__input"
                placeholder="ถามเกี่ยวกับฝุ่น ไฟป่า หรือท่องเที่ยว..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
              />
              <button
                type="button"
                className="ai-chat__send"
                onClick={handleSend}
                disabled={sending || !input.trim()}
                aria-label="ส่งข้อความ"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
