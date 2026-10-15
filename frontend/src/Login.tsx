import { FormEvent, useState } from "react";
import { api, setToken } from "./api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [f, setF] = useState({ email: "", name: "", password: "" });
  const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api<{ token: string }>(mode === "login" ? "/auth/login" : "/auth/register",
        { body: mode === "login" ? { email: f.email, password: f.password } : f });
      setToken(r.token);
      onDone();
    } catch (ex) { setErr((ex as Error).message); }
  }
  return (
    <form className="card login" onSubmit={submit}>
      <h2>QuickCare India support</h2>
      <input placeholder="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required />
      {mode === "register" && <input placeholder="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />}
      <input placeholder="Password (min 8)" type="password" minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required />
      {err && <p className="err">{err}</p>}
      <button type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
      <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === "login" ? "register" : "login"); }}>
        {mode === "login" ? "New here? Register" : "Have an account? Sign in"}
      </a>
    </form>
  );
}
