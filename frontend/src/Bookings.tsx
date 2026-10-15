import { useEffect, useState } from "react";
import { Appt, ConvSummary, api } from "./api";

export function Bookings({ refresh }: { refresh: number }) {
  const [list, setList] = useState<Appt[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Appt[]>("/appointments").then((items) => { setList(items); setError(""); })
      .catch((e: Error) => setError(e.message));
  }, [refresh]);
  return (
    <section className="card">
      <h3>My appointments</h3>
      {error ? <p className="err">Could not load appointments: {error}</p> : list.length === 0 && <p className="muted">None yet.</p>}
      {list.map((a) => (
        <div key={a.id} className="appt">
          <b>#{a.id} {a.service}</b> <span className={`badge ${a.status}`}>{a.status}</span>
          <div className="muted">{new Date(a.start_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })} · {a.city}</div>
          <div className="muted">{a.technician} · ₹{a.price_inr}{a.cancellation_fee_inr ? ` · fee ₹${a.cancellation_fee_inr}` : ""}</div>
        </div>
      ))}
    </section>
  );
}

export function History({ current, onPick, refresh }: { current: number | null; onPick: (id: number | null) => void; refresh: number }) {
  const [list, setList] = useState<ConvSummary[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<ConvSummary[]>("/conversations").then((items) => { setList(items); setError(""); })
      .catch((e: Error) => setError(e.message));
  }, [refresh, current]);
  return (
    <section className="card">
      <h3>History <button className="link" onClick={() => onPick(null)}>+ new</button></h3>
      {error && <p className="err">Could not load history: {error}</p>}
      {list.map((c) => (
        <div key={c.id} className={`hist ${c.id === current ? "active" : ""}`} onClick={() => onPick(c.id)}>
          Conversation #{c.id} <span className="muted">· {c.channel}{c.status === "handed_off" ? " · human" : ""}</span>
        </div>
      ))}
    </section>
  );
}
