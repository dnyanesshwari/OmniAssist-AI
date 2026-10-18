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
  const recognizing = useRef(false);
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
    recognizing.current = false;
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
    if (ws.current && ws.current.readyState <= WebSocket.OPEN) return;
    const token = getToken();
    if (!token) { hRef.current.onNotice("Sign in again before starting voice chat."); return; }
    const sock = new WebSocket(`${WS}/ws/voice?token=${encodeURIComponent(token)}${conversationId ? `&conversation_id=${conversationId}` : ""}`);
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
          audio.current = a;
          a.onended = () => setState((s) => s === "speaking" ? "listening" : s);
          setState("speaking");
          a.play().catch(() => { hRef.current.onNotice("Audio playback was blocked. Allow audio playback and try again."); setState("listening"); });
          break;
        }
        case "tts.cancel": stopPlayback(); setState("listening"); break;
        case "transcript.final": hRef.current.onUser(m.text); break;
        case "idle_prompt": hRef.current.onNotice("Still there? I'll stop listening soon if it stays quiet."); break;
        case "closing": hRef.current.onNotice("Voice session ended after a period of silence."); stop(); break;
        case "error": hRef.current.onNotice(m.message ?? "Voice error"); setState("listening"); break;
      }
    };
    sock.onerror = () => hRef.current.onNotice("Voice connection failed. Check that the backend is running and try again.");
    sock.onclose = () => {
      recognizing.current = false;
      rec.current?.stop?.();
      rec.current = null;
      setState("off");
    };
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
              if (text.trim() && sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify({ type: "transcript.final", text: text.trim() }));
            } else {
              setPartial(text);
              stopPlayback();                           // barge-in: stop speaking the moment the user talks
              if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify({ type: "transcript.partial", text }));
            }
          }
        };
        r.onerror = (e: any) => {
          if (e.error !== "aborted" && e.error !== "no-speech") hRef.current.onNotice(`Speech recognition failed: ${e.error ?? "unknown error"}`);
        };
        r.onend = () => {
          if (ws.current !== sock || !recognizing.current || sock.readyState !== WebSocket.OPEN) return;
          window.setTimeout(() => {
            if (ws.current === sock && recognizing.current && sock.readyState === WebSocket.OPEN) {
              try { r.start(); } catch { /* recognition may already be starting */ }
            }
          }, 200);
        };
        recognizing.current = true;
        r.start();
        rec.current = r;
      } else {
        hRef.current.onNotice(typeof navigator.mediaDevices?.getUserMedia === "function"
          ? "Speech recognition is unavailable. Hold the mic button to record your message."
          : "This browser does not support microphone access. You can still type a message.");
      }
    };
  }, [conversationId, onConversation, speak, stop, stopPlayback]);

  // push-to-talk fallback (server-side ASR)
  const recordStart = useCallback(async () => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      hRef.current.onNotice("Microphone recording is unavailable in this browser. You can still type a message.");
      return;
    }
    stopPlayback();
    ws.current.send(JSON.stringify({ type: "interrupt" }));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      mr.ondataavailable = async (e) => {
        if (!e.data.size || ws.current?.readyState !== WebSocket.OPEN) return;
        const bytes = new Uint8Array(await e.data.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ type: "audio.chunk", mime: mr.mimeType || "audio/webm", data: btoa(bin) }));
      };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ type: "audio.end" }));
      };
      mr.start(250);
      media.current = mr;
    } catch (error) {
      hRef.current.onNotice(`Microphone access failed: ${(error as Error).message || "allow microphone access and try again"}`);
    }
  }, [stopPlayback]);
  const recordStop = useCallback(() => { if (media.current?.state === "recording") media.current.stop(); }, []);

  useEffect(() => {
    return () => { stop(); };
  }, [stop]);
  const hasBrowserAsr = typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  return { state, partial, start, stop, recordStart, recordStop, hasBrowserAsr };
}
