import { useCallback, useEffect, useState } from "react";
import Admin from "./Admin";
import { Bookings, History } from "./Bookings";
import Chat from "./Chat";
import Login from "./Login";
import { Me, api, getToken, setToken } from "./api";

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [authed, setAuthed] = useState(!!getToken());
  const [conv, setConv] = useState<number | null>(null);
  const [tab, setTab] = useState<"chat" | "admin">("chat");
  const [tick, setTick] = useState(0);
  const bump = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!authed) return;
    api<Me>("/me").then(setMe).catch(() => { setToken(null); setAuthed(false); });
  }, [authed]);

  if (!authed) return <div className="center"><Login onDone={() => setAuthed(true)} /></div>;
  return (
    <div className="app">
      <header>
        <b>OmniAssist AI</b><span className="muted"> · QuickCare India</span>
        <nav>
          <button className={tab === "chat" ? "on" : ""} onClick={() => setTab("chat")}>Support</button>
          {me?.is_admin && <button className={tab === "admin" ? "on" : ""} onClick={() => setTab("admin")}>Analytics</button>}
          <button className="link" onClick={() => { setToken(null); setAuthed(false); setMe(null); setConv(null); }}>Sign out{me ? ` (${me.name})` : ""}</button>
        </nav>
      </header>
      {tab === "admin" ? <Admin /> : (
        <main>
          <aside><History current={conv} onPick={setConv} refresh={tick} /><Bookings refresh={tick} /></aside>
          <Chat conversationId={conv} setConversationId={(id) => { setConv(id); bump(); }} onBookingChange={bump} />
        </main>
      )}
    </div>
  );
}
