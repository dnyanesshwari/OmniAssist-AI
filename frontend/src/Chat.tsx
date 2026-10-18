import { useCallback, useEffect, useRef, useState } from "react";
import { Msg, TurnResult, api } from "./api";
import { useVoice } from "./useVoice";

interface Props {
  conversationId: number | null;
  setConversationId: (id: number) => void;
  onBookingChange: () => void;
}

export default function Chat({ conversationId, setConversationId, onBookingChange }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [handoff, setHandoff] = useState<number | null>(null);
  const pendingVoice = useRef<string[]>([]);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setHandoff(null);
    if (!conversationId) {
      setLoadError("");
      if (!pendingVoice.current.length) setMsgs([]);
      if (pendingVoice.current.length) {
        setMsgs(pendingVoice.current.map((content) => ({ role: "user", content, modality: "voice" })));
        pendingVoice.current = [];
      }
      return;
    }
    api<Msg[]>(`/conversations/${conversationId}/messages`)
      .then((m) => { setMsgs(m.filter((x) => x.role !== ("tool" as string))); setLoadError(""); })
      .catch((e: Error) => setLoadError(e.message));
  }, [conversationId]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const applyResult = useCallback((r: TurnResult) => {
    setMsgs((m) => [...m, { role: "assistant", content: r.reply, citations: r.citations }]);
    if (r.handoff && r.ticket_id) setHandoff(r.ticket_id);
    if (r.appointment || r.intent === "confirmation") onBookingChange();
  }, [onBookingChange]);

  const voice = useVoice(conversationId, {
    onUser: (t) => {
      setMsgs((m) => [...m, { role: "user", content: t, modality: "voice" }]);
      if (!conversationId) pendingVoice.current.push(t);
    },
    onAssistant: applyResult,
    onNotice: setNotice,
  }, setConversationId);

  async function send(t: string) {
    if (!t.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", content: t, modality: "text" }]);
    setText(""); setBusy(true); setNotice("");
    try {
      const r = await api<TurnResult>("/chat/message", { body: { text: t, conversation_id: conversationId } });
      setConversationId(r.conversation_id);
      applyResult(r);
    } catch (ex) {
      setMsgs((m) => [...m, { role: "assistant", content: `⚠️ ${(ex as Error).message}` }]);
    } finally { setBusy(false); }
  }

  async function escalate() {
    if (!conversationId) return;
    try {
      const r = await api<{ ticket_id: number }>(`/conversations/${conversationId}/handoff`, { method: "POST", body: {} });
      setHandoff(r.ticket_id);
      setMsgs((m) => [...m, { role: "assistant", content: `A human agent has been notified (ticket #${r.ticket_id}).` }]);
    } catch (error) {
      setNotice((error as Error).message);
    }
  }

  return (
    <section className="card chat">
      <div className="messages">
        {loadError && <p className="err">Could not load this conversation: {loadError}</p>}
        {msgs.length === 0 && <p className="muted">Ask about pricing, warranty or cancellation, or say “book an AC service in Pune tomorrow at 11”.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.modality === "voice" && <span className="tag">🎙</span>}
            <span>{m.content.replace(/\*\*/g, "")}</span>
            {m.citations && m.citations.length > 0 && (
              <div className="cites">
                {m.citations.map((c) => {
                  const key = `${i}-${c.ref}`;
                  return (
                    <button key={key} className="chip" onClick={() => setOpen(open === key ? null : key)}>
                      [{c.ref}] {c.document}{c.section ? ` › ${c.section}` : ""}
                    </button>
                  );
                })}
                {m.citations.map((c) => open === `${i}-${c.ref}` && <blockquote key={c.ref}>{c.snippet}…</blockquote>)}
              </div>
            )}
          </div>
        ))}
        {voice.partial && <div className="bubble user partial">{voice.partial}…</div>}
        {busy && <div className="bubble assistant muted">Thinking…</div>}
        <div ref={bottom} />
      </div>
      {handoff && <div className="banner">Handed off to a human agent — ticket #{handoff}</div>}
      {notice && <div className="banner warn">{notice}</div>}
      <div className="composer">
        {voice.state === "off" ? (
          <button className="mic" title="Start voice" onClick={voice.start}>🎙</button>
        ) : (
          <button className="mic live" title="Stop voice" onClick={voice.stop}>⏹ {voice.state}</button>
        )}
        {voice.state !== "off" && !voice.hasBrowserAsr && (
          <button className="mic" onMouseDown={voice.recordStart} onMouseUp={voice.recordStop}>Hold to talk</button>
        )}
        <input value={text} placeholder="Type a message…" onChange={(e) => setText(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && send(text)} />
        <button onClick={() => send(text)} disabled={busy}>Send</button>
      </div>
      <div className="tools">
        <button className="link" onClick={escalate} disabled={!conversationId}>Talk to a human</button>
      </div>
    </section>
  );
}
