import { useCallback, useEffect, useRef, useState } from "react";
import { TurnResult, WS, getToken } from "./api";

/* eslint-disable @typescript-eslint/no-explicit-any */
interface Handlers {
  onUser: (text: string) => void;                 // finalized user utterance (voice)
  onAssistant: (r: TurnResult) => void;
  onNotice: (text: string) => void;
}
export type VoiceState = "off" | "listening" | "thinking" | "speaking";

export function useVoice(conversationId: number | null, h: Handlers, onConversation: (id: number) => void) {
  const [state, setState] = useState<VoiceState>("off");
  const [partial, setPartial] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const rec = useRef<any>(null);
  const media = useRef<MediaRecorder | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const hRef = useRef(h);
  hRef.current = h;

  const stopPlayback = useCallback(() => {
    window.speechSynthesis?.cancel();
    audio.current?.pause();
    audio.current = null;
  }, []);

  const speak = useCallback((text: string) => {
    if (!window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text.replace(/\*\*/g, ""));
    u.lang = "en-IN";
    u.onstart = () => setState("speaking");
    u.onend = () => setState((s) => (s === "speaking" ? "listening" : s));
    window.speechSynthesis.speak(u);
  }, []);

  const stop = useCallback(() => {
    rec.current?.stop?.();
    rec.current = null;
    if (media.current && media.current.state !== "inactive") media.current.stop();
    stopPlayback();
    ws.current?.close();
    ws.current = null;
    setState("off");
    setPartial("");
  }, [stopPlayback]);

  const start = useCallback(() => {
    const sock = new WebSocket(`${WS}/ws/voice?token=${getToken()}${conversationId ? `&conversation_id=${conversationId}` : ""}`);
    ws.current = sock;
    sock.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "ready": if (m.conversation_id) onConversation(m.conversation_id); break;
        case "assistant.thinking": setState("thinking"); break;
        case "assistant.text":
          onConversation(m.conversation_id);
          hRef.current.onAssistant(m as TurnResult);
          if (m.reply) speak(m.reply);
          else setState("listening");
          break;
        case "tts.audio": {
          window.speechSynthesis?.cancel();           // server audio replaces browser speech
          const a = new Audio(`data:${m.mime};base64,${m.data}`);
          audio.current = a; a.play().catch(() => undefined); break;
        }
        case "tts.cancel": stopPlayback(); setState("listening"); break;
        case "transcript.final": hRef.current.onUser(m.text); break;
        case "idle_prompt": hRef.current.onNotice("Still there? I'll stop listening soon if it stays quiet."); break;
        case "closing": hRef.current.onNotice("Voice session ended after a period of silence."); stop(); break;
        case "error": hRef.current.onNotice(m.message ?? "Voice error"); setState("listening"); break;
      }
    };
    sock.onclose = () => setState("off");
    sock.onopen = () => {
      setState("listening");
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SR) {                                        // primary path: browser ASR with interim results
        const r = new SR();
        r.continuous = true; r.interimResults = true; r.lang = "en-IN";
        r.onresult = (e: any) => {
          for (let i = e.resultIndex; i < e.results.length; i++) {
            const text: string = e.results[i][0].transcript;
            if (e.results[i].isFinal) {
              setPartial("");
              hRef.current.onUser(text.trim());
              sock.send(JSON.stringify({ type: "transcript.final", text }));
            } else {
              setPartial(text);
              stopPlayback();                           // barge-in: stop speaking the moment the user talks
              sock.send(JSON.stringify({ type: "transcript.partial", text }));
            }
          }
        };
        r.onend = () => { if (ws.current === sock) { try { r.start(); } catch { /* already started */ } } };
        r.start();
        rec.current = r;
      } else {
        hRef.current.onNotice("This browser has no speech recognition. Hold the mic button to record instead.");
      }
    };
  }, [conversationId, onConversation, speak, stop, stopPlayback]);

  // push-to-talk fallback (server-side ASR)
  const recordStart = useCallback(async () => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    stopPlayback();
    ws.current.send(JSON.stringify({ type: "interrupt" }));
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream);
    mr.ondataavailable = async (e) => {
      const buf = new Uint8Array(await e.data.arrayBuffer());
      let bin = ""; buf.forEach((b) => (bin += String.fromCharCode(b)));
      ws.current?.send(JSON.stringify({ type: "audio.chunk", mime: mr.mimeType, data: btoa(bin) }));
    };
    mr.onstop = () => { stream.getTracks().forEach((t) => t.stop()); ws.current?.send(JSON.stringify({ type: "audio.end" })); };
    mr.start();
    media.current = mr;
  }, [stopPlayback]);
  const recordStop = useCallback(() => { if (media.current?.state === "recording") media.current.stop(); }, []);

  useEffect(() => {
    return () => { stop(); };
  }, [stop]);
  const hasBrowserAsr = typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  return { state, partial, start, stop, recordStart, recordStop, hasBrowserAsr };
}
