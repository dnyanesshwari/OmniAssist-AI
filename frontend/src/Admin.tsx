import { useEffect, useState } from "react";
import { api } from "./api";

interface Analytics {
  conversations: number; messages: number;
  handoffs: { total: number; by_reason: Record<string, number>; rate: number };
  appointments_by_status: Record<string, number>;
  rag: { answers: number; abstained: number };
  intents: Record<string, number>;
  tools: Record<string, { ok: number; error: number }>;
  latency_ms: { p50: number | null; p95: number | null };
}

const Stat = ({ k, v }: { k: string; v: string | number }) => <div className="stat"><b>{v}</b><span>{k}</span></div>;

export default function Admin() {
  const [a, setA] = useState<Analytics | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<Analytics>("/admin/analytics").then(setA).catch((e) => setErr(e.message)); }, []);
  if (err) return <p className="err">{err}</p>;
  if (!a) return <p className="muted">Loading…</p>;
  const abst = a.rag.answers ? Math.round((100 * a.rag.abstained) / a.rag.answers) : 0;
  return (
    <section className="card admin">
      <h3>Analytics</h3>
      <div className="stats">
        <Stat k="conversations" v={a.conversations} /><Stat k="messages" v={a.messages} />
        <Stat k="human handoffs" v={`${a.handoffs.total} (${Math.round(a.handoffs.rate * 100)}%)`} />
        <Stat k="RAG abstain rate" v={`${abst}%`} />
        <Stat k="p50 / p95 ms" v={`${a.latency_ms.p50 ?? "–"} / ${a.latency_ms.p95 ?? "–"}`} />
      </div>
      <div className="cols">
        <Table title="Appointments" rows={Object.entries(a.appointments_by_status)} />
        <Table title="Intents" rows={Object.entries(a.intents)} />
        <Table title="Handoff reasons" rows={Object.entries(a.handoffs.by_reason)} />
        <Table title="Tool calls (ok / error)" rows={Object.entries(a.tools).map(([k, v]) => [k, `${v.ok} / ${v.error}`])} />
      </div>
    </section>
  );
}

function Table({ title, rows }: { title: string; rows: [string, string | number][] }) {
  return (
    <div><h4>{title}</h4>
      <table><tbody>{rows.length ? rows.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>) : <tr><td className="muted">no data</td></tr>}</tbody></table>
    </div>
  );
}
