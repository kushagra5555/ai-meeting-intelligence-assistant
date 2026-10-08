import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronRight,
  CircleStop,
  Clock3,
  Download,
  FileAudio,
  ListChecks,
  Mic,
  Pause,
  Play,
  Plus,
  Search,
  Share2,
  Sparkles,
} from "lucide-react";
import "./styles.css";
import "./overrides.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
// Browser speech captions can insert generic phrases that were never spoken.
// The prototype uses Gemini's dedicated transcription path instead.
const ENABLE_UNVERIFIED_BROWSER_CAPTIONS = false;
if (!ENABLE_UNVERIFIED_BROWSER_CAPTIONS) {
  try {
    (window as any).SpeechRecognition = undefined;
    (window as any).webkitSpeechRecognition = undefined;
  } catch {}
}
type Segment = {
  id?: number;
  start_time: number;
  end_time: number;
  speaker: string;
  text: string;
};
type Intelligence = {
  summary: string;
  key_points: string[];
  decisions: string[];
  action_items: {
    task: string;
    owner?: string | null;
    deadline?: string | null;
    priority?: string;
  }[];
};
type Meeting = {
  id: string;
  title: string;
  date: string;
  participants: string;
  duration: number;
  audio_path?: string;
  status: string;
  action_items_count: number;
  transcript?: Segment[];
  intelligence?: Intelligence | null;
  speaker_identity?: Record<string, { participant_name?: string | null; confidence?: number; evidence?: string }>;
};
const api = async (path: string, options?: RequestInit) => {
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
};
const fmt = (s: number) => {
  const m = Math.floor(s / 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${Math.floor(s % 60)
    .toString()
    .padStart(2, "0")}`;
};
const dateLabel = (d: string) =>
  new Date(`${d}T12:00:00`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

function App() {
  const [page, setPage] = useState<"home" | "new" | "record" | "result">(
    "home",
  );
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    api("/meetings")
      .then(setMeetings)
      .catch(() => setMeetings([]));
  }, [refresh]);
  const open = async (id: string) => {
    setSelected(await api(`/meetings/${id}`));
    setPage("result");
  };
  if (page === "new")
    return (
      <NewMeeting
        onBack={() => setPage("home")}
        onCreated={(m) => {
          setSelected(m);
          setPage("record");
        }}
      />
    );
  if (page === "record" && selected)
    return (
      <Recorder
        meeting={selected}
        onDone={async () => {
          setSelected(await api(`/meetings/${selected.id}`));
          setPage("result");
          setRefresh((x) => x + 1);
        }}
      />
    );
  if (page === "result" && selected)
    return (
      <Results
        meeting={selected}
        onBack={() => {
          setPage("home");
          setRefresh((x) => x + 1);
        }}
      />
    );
  return (
    <Dashboard meetings={meetings} onNew={() => setPage("new")} onOpen={open} />
  );
}

function Shell({
  children,
  onNew,
}: {
  children: React.ReactNode;
  onNew?: () => void;
}) {
  return (
    <div className="app">
      <aside>
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={17} />
          </div>
          <span><b>kushagra.ai</b></span>
        </div>
        <div className="nav active">
          <FileAudio size={17} /> Meetings
        </div>
        <div className="side-note">
          <div className="pulse" />
          <span>
            Local workspace
            <br />
            <small>Your audio stays private</small>
          </span>
        </div>
      </aside>
      <main>
        <header>
          <div className="eyebrow">WORKSPACE / MEETINGS</div>
          {onNew && (
            <button className="primary small" onClick={onNew}>
              <Plus size={17} /> New meeting
            </button>
          )}
        </header>
        {children}
      </main>
    </div>
  );
}
function Dashboard({
  meetings,
  onNew,
  onOpen,
}: {
  meetings: Meeting[];
  onNew: () => void;
  onOpen: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const filtered = meetings.filter((x) =>
    x.title.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <Shell onNew={onNew}>
      <section className="hero">
        <div>
          <div className="kicker">
            <span className="dot" /> PRIVATE AI WORKSPACE
          </div>
          <h1>
            Make every conversation
            <br />
            <em>move forward.</em>
          </h1>
          <p>
            Capture the signal in your meetings with local-first transcription
            and focused intelligence.
          </p>
        </div>
        <div className="hero-orb">
          <Sparkles size={28} />
          <div />
        </div>
      </section>
      <div className="section-head">
        <div>
          <h2>Recent meetings</h2>
          <p>
            {meetings.length
              ? `${meetings.length} conversations in your workspace`
              : "Your meeting library is ready when you are."}
          </p>
        </div>
        <div className="search">
          <Search size={16} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search meetings"
          />
        </div>
      </div>
      {filtered.length ? (
        <div className="meeting-grid">
          {filtered.map((m) => (
            <button
              className="meeting-card"
              key={m.id}
              onClick={() => onOpen(m.id)}
            >
              <div className="card-top">
                <span className="date">
                  <CalendarDays size={14} />
                  {dateLabel(m.date)}
                </span>
                <ChevronRight size={17} />
              </div>
              <h3>{m.title}</h3>
              <div className="card-meta">
                <span>
                  <Clock3 size={14} />
                  {fmt(m.duration || 0)}
                </span>
                <span>
                  <ListChecks size={14} />
                  {m.action_items_count || 0} action items
                </span>
              </div>
              <div className="card-line">
                <span className={`status ${m.status}`}>
                  {m.status === "processing" ? "PROCESSING" : "READY"}
                </span>
                <span>Open meeting</span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty">
          <div className="empty-icon">
            <Mic size={24} />
          </div>
          <h3>No meetings yet</h3>
          <p>
            Start your first conversation and see the intelligence build itself.
          </p>
          <button className="primary" onClick={onNew}>
            <Plus size={18} /> Create first meeting
          </button>
        </div>
      )}
    </Shell>
  );
}

function NewMeeting({
  onBack,
  onCreated,
}: {
  onBack: () => void;
  onCreated: (m: Meeting) => void;
}) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [participants, setParticipants] = useState("");
  const [error, setError] = useState("");
  const submit = async () => {
    if (!title.trim()) return setError("Give your meeting a title first.");
    if (!participants.trim()) return setError("Add the participant names so AI speaker identification can work.");
    try {
      const { id } = await api("/meetings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, date, participants }),
      });
      onCreated({
        id,
        title,
        date,
        participants,
        duration: 0,
        status: "ready",
        action_items_count: 0,
      });
    } catch {
      setError("Could not create the meeting. Is the backend running?");
    }
  };
  return (
    <Shell>
      <div className="form-wrap">
        <button className="back" onClick={onBack}>
          <ArrowLeft size={16} /> All meetings
        </button>
        <div className="form-heading">
          <div className="kicker">
            <span className="dot" /> NEW SESSION
          </div>
          <h1>
            Set the room
            <br />
            <em>in motion.</em>
          </h1>
          <p>Add a little context before you start recording.</p>
        </div>
        <div className="form-card">
          <label>
            Meeting title
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Website Launch Discussion"
            />
          </label>
          <div className="two">
            <label>
              Date
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label>
              Participants <span className="muted">required for speaker identification</span>
              <input
                value={participants}
                onChange={(e) => setParticipants(e.target.value)}
                placeholder="Enter participant names"
              />
            </label>
          </div>
          {error && <div className="error">{error}</div>}
          <button className="primary wide" onClick={submit}>
            <Mic size={18} /> Start recording <ChevronRight size={17} />
          </button>
          <div className="privacy">
            <span>
              <Check size={13} />
            </span>{" "}
            Recorded locally in your browser
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Recorder({
  meeting,
  onDone,
}: {
  meeting: Meeting;
  onDone: () => void;
}) {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [error, setError] = useState("");
  const [meetingAudio, setMeetingAudio] = useState(false);
  const [levels, setLevels] = useState({ mic: 0, meeting: 0, mixed: 0 });
  const [captureInfo, setCaptureInfo] = useState({ micTracks: 0, meetingTracks: 0, micChannels: 0, meetingChannels: 0 });
  const media = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const chunkRecorder = useRef<MediaRecorder | null>(null);
  const chunkTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chunkLength = useRef(8);
  const rawStreams = useRef<MediaStream[]>([]);
  const audioContext = useRef<AudioContext | null>(null);
  const assemblySockets = useRef<WebSocket[]>([]);
  const assemblyProcessors = useRef<ScriptProcessorNode[]>([]);
  const assemblySources = useRef<MediaStreamAudioSourceNode[]>([]);
  const micAnalyser = useRef<AnalyserNode | null>(null);
  const meetingAnalyser = useRef<AnalyserNode | null>(null);
  const mixedAnalyser = useRef<AnalyserNode | null>(null);
  const meterTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRef = useRef(false);
  const recognition = useRef<any>(null);
  const finalSegments = useRef<Segment[]>([]);
  const startRef = useRef(0);
  useEffect(() => {
    let t: any;
    if (recording && !paused)
      t = setInterval(
        () => setSeconds(Math.floor((Date.now() - startRef.current) / 1000)),
        500,
      );
    return () => clearInterval(t);
  }, [recording, paused]);
  const startChunk = (stream: MediaStream, startTime = 0, duration = chunkLength.current) => {
    if (!activeRef.current) return;
    const recorder = new MediaRecorder(stream);
    const parts: Blob[] = [];
    chunkRecorder.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) parts.push(event.data);
    };
    recorder.onstop = async () => {
      const audio = new Blob(parts, { type: recorder.mimeType || "audio/webm" });
      if (audio.size) {
        try {
          const form = new FormData();
          form.append("file", audio, "live-chunk.webm");
          const result = await api(
            `/meetings/${meeting.id}/recording/chunk?start_time=${startTime}`,
            { method: "POST", body: form },
          );
          if (result.retryable) {
            chunkLength.current = Math.max(20, chunkLength.current * 2);
            setError(`Gemini rate-limited live updates. Continuing with ${chunkLength.current}-second audio windows.`);
          } else if (result.error) setError(result.error);
          else setError("");
          if (result.segments?.length)
            setSegments((current) => [...current, ...result.segments]);
        } catch {
          // The final recording remains available even if one live chunk fails.
        }
      }
      if (activeRef.current) startChunk(stream, startTime + duration, duration);
    };
    recorder.start();
    chunkTimer.current = setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, duration * 1000);
  };
  const readLevel = (analyser: AnalyserNode | null) => {
    if (!analyser) return 0;
    const values = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(values);
    let sum = 0;
    for (const value of values) {
      const normalized = (value - 128) / 128;
      sum += normalized * normalized;
    }
    return Math.min(1, Math.sqrt(sum / values.length) * 4);
  };
  const startAssemblyLive = (stream: MediaStream, sourceName: "mic" | "meeting") => {
    const ctx = audioContext.current;
    if (!ctx || !activeRef.current) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.hostname}:8000/api/meetings/${meeting.id}/assembly-live?source=${sourceName}`);
    assemblySockets.current.push(socket);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "error") { setError(data.message); return; }
      if (data.type === "interim") {
        setSegments((current) => [...current.filter((item) => item.end_time !== 0), { start_time: data.start_time || 0, end_time: 0, speaker: "Listening…", text: data.text }]);
      }
      if (data.type === "final") {
        setError("");
        setSegments((current) => [...current.filter((item) => item.end_time !== 0), { start_time: data.start_time, end_time: data.end_time, speaker: data.speaker || "Speaker 1", text: data.text }]);
      }
    };
    socket.onerror = () => setError("AssemblyAI live transcription could not connect. Recording will continue and Gemini will process the final audio.");
    const source = ctx.createMediaStreamSource(stream);
    // 4096 samples produces roughly 85–93 ms at common browser sample rates,
    // safely inside AssemblyAI's required 50–1000 ms PCM frame window.
    const processor = ctx.createScriptProcessor(4096, 1, 1);
    const silent = ctx.createGain();
    silent.gain.value = 0;
    source.connect(processor);
    processor.connect(silent);
    silent.connect(ctx.destination);
    assemblySources.current.push(source);
    assemblyProcessors.current.push(processor);
    processor.onaudioprocess = (event) => {
      if (socket.readyState !== WebSocket.OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      const ratio = event.inputBuffer.sampleRate / 16000;
      const output = new Int16Array(Math.floor(input.length / ratio));
      for (let index = 0; index < output.length; index++) {
        const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
        output[index] = sample < 0 ? sample * 32768 : sample * 32767;
      }
      socket.send(output.buffer);
    };
  };
  const begin = async () => {
    try {
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        },
      });
      let tab: MediaStream | null = null;
      try {
        tab = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: true,
        });
      } catch {
        setError(
          "Meeting audio was not shared. Start again, select the call tab or window, and enable Share audio.",
        );
        mic.getTracks().forEach((track) => track.stop());
        return;
      }
      const hasCallAudio = Boolean(tab?.getAudioTracks().length);
      setMeetingAudio(hasCallAudio);
      if (!hasCallAudio) {
        setError(
          "Meeting audio is not being captured. Select the meeting tab/window and enable Share audio.",
        );
        mic.getTracks().forEach((track) => track.stop());
        tab?.getTracks().forEach((track) => track.stop());
        return;
      }
      tab.getAudioTracks()[0]?.addEventListener("ended", () => {
        if (activeRef.current) {
          setMeetingAudio(false);
          setError("Meeting audio sharing ended. Restart and share the call tab with Share audio enabled.");
        }
      });
      const ctx = new AudioContext();
      await ctx.resume();
      const destination = ctx.createMediaStreamDestination();
      const micSource = ctx.createMediaStreamSource(mic);
      const meetingSource = ctx.createMediaStreamSource(tab);
      const micGain = ctx.createGain();
      const meetingGain = ctx.createGain();
      micGain.gain.value = 1;
      meetingGain.gain.value = 1;
      const micMeter = ctx.createAnalyser();
      const meetingMeter = ctx.createAnalyser();
      const mixedMeter = ctx.createAnalyser();
      micMeter.fftSize = 512;
      meetingMeter.fftSize = 512;
      mixedMeter.fftSize = 512;
      micSource.connect(micGain).connect(destination);
      meetingSource.connect(meetingGain).connect(destination);
      micGain.connect(micMeter);
      meetingGain.connect(meetingMeter);
      ctx.createMediaStreamSource(destination.stream).connect(mixedMeter);
      const stream = new MediaStream(destination.stream.getAudioTracks());
      rawStreams.current = [mic, ...(tab ? [tab] : [])];
      audioContext.current = ctx;
      micAnalyser.current = micMeter;
      meetingAnalyser.current = meetingMeter;
      mixedAnalyser.current = mixedMeter;
      setCaptureInfo({
        micTracks: mic.getAudioTracks().length,
        meetingTracks: tab.getAudioTracks().length,
        micChannels: mic.getAudioTracks()[0]?.getSettings().channelCount || 1,
        meetingChannels: tab.getAudioTracks()[0]?.getSettings().channelCount || 1,
      });
      const rec = new MediaRecorder(stream);
      media.current = rec;
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.start(1000);
      startRef.current = Date.now();
      activeRef.current = true;
      setRecording(true);
      startAssemblyLive(mic, "mic");
      if (tab) startAssemblyLive(tab, "meeting");
      meterTimer.current = setInterval(() => setLevels({ mic: readLevel(micAnalyser.current), meeting: readLevel(meetingAnalyser.current), mixed: readLevel(mixedAnalyser.current) }), 180);
    } catch {
      setError(
        "Microphone or tab audio permission was denied. Allow both permissions and try again.",
      );
    }
  };
  const stop = async () => {
    if (!media.current) return;
    activeRef.current = false;
    if (chunkTimer.current) clearTimeout(chunkTimer.current);
    if (chunkRecorder.current?.state === "recording") chunkRecorder.current.stop();
    assemblyProcessors.current.forEach((processor) => processor.disconnect());
    assemblySources.current.forEach((source) => source.disconnect());
    assemblySockets.current.forEach((socket) => socket.close());
    assemblyProcessors.current = [];
    assemblySources.current = [];
    assemblySockets.current = [];
    if (meterTimer.current) clearInterval(meterTimer.current);
    const recorder = media.current;
    const stopComplete = new Promise<void>((resolve) => {
      recorder.addEventListener("stop", () => resolve(), { once: true });
    });
    recorder.stop();
    rawStreams.current.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    audioContext.current?.close();
    recognition.current?.stop();
    setRecording(false);
    setLevels({ mic: 0, meeting: 0, mixed: 0 });
    await stopComplete;
    const blob = new Blob(chunks.current, {
      type: recorder.mimeType || "audio/webm",
    });
    if (!blob.size) {
      setError(
        "The browser did not return any audio data. Please check microphone permissions and try again.",
      );
      return;
    }
    const fd = new FormData();
    fd.append("file", blob, "meeting.webm");
    await api(`/meetings/${meeting.id}/recording?duration=${seconds}`, {
      method: "POST",
      body: fd,
    });
    try {
      await api(`/meetings/${meeting.id}/process`, { method: "POST" });
    } catch (e) {
      setError(
        "Audio was saved, but transcription could not complete. Please try again.",
      );
    }
    onDone();
  };
  return (
    <Shell>
      <div className="record-page">
        <button className="back" onClick={onDone}>
          <ArrowLeft size={16} /> Leave recording
        </button>
        <div className="record-header">
          <div>
            <div className="kicker">
              <span className={`live-dot ${recording ? "on" : ""}`} />{" "}
              {recording ? "RECORDING IN PROGRESS" : "READY TO RECORD"}
            </div>
            <h1>{meeting.title}</h1>
            <p>
              {dateLabel(meeting.date)}{" "}
              {meeting.participants && `· ${meeting.participants}`}
            </p>
          </div>
          <div className="timer">
            {fmt(seconds)}
            <small>ELAPSED</small>
          </div>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="record-controls">
          {!recording ? (
            <button className="primary record-btn" onClick={begin}>
              <Mic size={20} /> Start recording + share audio
            </button>
          ) : (
            <>
              <button
                className="control"
                onClick={() => {
                  if (paused) {
                    media.current?.resume();
                    setPaused(false);
                  } else {
                    media.current?.pause();
                    setPaused(true);
                  }
                }}
              >
                {paused ? <Play size={18} /> : <Pause size={18} />}{" "}
                {paused ? "Resume" : "Pause"}
              </button>
              <button className="stop" onClick={stop}>
                <CircleStop size={18} /> Stop meeting
              </button>
            </>
          )}
        </div>
        <div className="capture-tip">
          For WhatsApp, Meet, or another browser call: choose the call tab in
          the sharing dialog and enable <b>Share audio</b>.
        </div>
        <div className="audio-diagnostics">
          <div className="diagnostics-title">Audio capture diagnostics</div>
          <div className="meter-row"><span>Microphone</span><div className="meter-track"><i style={{ width: `${Math.round(levels.mic * 100)}%` }} /></div><b>{meetingAudio ? "Active" : "Waiting"}</b></div>
          <div className="meter-row"><span>Meeting audio</span><div className="meter-track"><i className={meetingAudio && levels.meeting > 0.02 ? "meeting" : "missing"} style={{ width: `${Math.round(levels.meeting * 100)}%` }} /></div><b>{!meetingAudio ? "Missing" : levels.meeting > 0.02 ? "Signal" : "No signal"}</b></div>
          <div className="diagnostics-meta">Tracks — mic: {captureInfo.micTracks} · meeting: {captureInfo.meetingTracks} · mixed output: {recording ? "Active" : "Idle"}</div>
        </div>
        <div className="live-panel">
          <div className="panel-head">
            <span>
              <span className="mini-wave">∿</span> Live transcript
            </span>
            <span className="muted">
          {recording
            ? meetingAudio
              ? "AssemblyAI live transcription"
              : "Listening to microphone only"
                : "Your words will appear here"}
            </span>
          </div>
          {segments.length ? (
            <div className="transcript">
              {segments.map((s, i) => (
                <div className="segment" key={i}>
                  <span className="segment-time">{fmt(s.start_time)}</span>
                  <div>
                    <b>{s.speaker}</b>
                    <p>{s.text}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="transcript-empty">
              <Mic size={21} />
              <p>
                Start recording to see your conversation
                <br />
                transcribed in real time.
              </p>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}

function Results({
  meeting,
  onBack,
}: {
  meeting: Meeting;
  onBack: () => void;
}) {
  const [ask, setAsk] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>({});
  const [editingSpeakers, setEditingSpeakers] = useState(false);
  const [savingSpeakers, setSavingSpeakers] = useState(false);
  const i = meeting.intelligence;
  const speakers = Array.from(new Set((meeting.transcript || []).map((segment) => segment.speaker)));
  const identityIds = Object.keys(meeting.speaker_identity || {});
  const editableSpeakers = identityIds.length ? identityIds : speakers;
  useEffect(() => {
    setSpeakerNames(Object.fromEntries(editableSpeakers.map((speaker) => [speaker, meeting.speaker_identity?.[speaker]?.participant_name || speaker])));
    setEditingSpeakers(false);
  }, [meeting.id, meeting.transcript, meeting.speaker_identity]);
  const saveSpeakerNames = async () => {
    setSavingSpeakers(true);
    try {
      await api(`/meetings/${meeting.id}/speakers`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names: speakerNames }),
      });
      setEditingSpeakers(false);
      window.location.reload();
    } finally {
      setSavingSpeakers(false);
    }
  };
  const audio = meeting.audio_path
    ? `http://localhost:8000/audio/${meeting.audio_path}`
    : undefined;
  const audioRef = useRef<HTMLAudioElement>(null);
  const seek = (time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      audioRef.current.play();
    }
  };
  const download = (name: string, content: string, type = "text/plain") => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const exportTranscript = () =>
    download(
      `${meeting.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-transcript.txt`,
      (meeting.transcript || [])
        .map((s) => `[${fmt(s.start_time)}] ${s.speaker}: ${s.text}`)
        .join("\n"),
    );
  const addCalendar = () => {
    const start = new Date(`${meeting.date}T09:00:00`);
    const end = new Date(start.getTime() + (meeting.duration || 30) * 60000);
    const stamp = (d: Date) =>
      d
        .toISOString()
        .replace(/[-:]/g, "")
        .replace(/\.\d{3}/, "");
    download(
      `${meeting.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.ics`,
      `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nDTSTART:${stamp(start)}\nDTEND:${stamp(end)}\nSUMMARY:${meeting.title}\nDESCRIPTION:kushagra.ai recording\nEND:VEVENT\nEND:VCALENDAR\n`,
      "text/calendar",
    );
  };
  const share = async () => {
    const text = `${meeting.title} — kushagra.ai`;
    if (navigator.share) await navigator.share({ title: meeting.title, text });
    else await navigator.clipboard?.writeText(text);
  };
  const submit = async () => {
    if (!ask.trim()) return;
    setAsking(true);
    try {
      setAnswer(
        (
          await api(`/meetings/${meeting.id}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: ask }),
          })
        ).answer,
      );
    } catch {
      setAnswer("Could not reach Gemini. Restart the backend and try again.");
    } finally {
      setAsking(false);
    }
  };
  return (
    <Shell>
      <div className="results">
        <button className="back" onClick={onBack}>
          <ArrowLeft size={16} /> All meetings
        </button>
        <div className="result-head">
          <div>
            <div className="kicker">
              <span className="dot" /> MEETING READY
            </div>
            <h1>{meeting.title}</h1>
            <p>
              {dateLabel(meeting.date)} · {fmt(meeting.duration)} ·{" "}
              {meeting.participants || "Private session"}
            </p>
          </div>
          <div className="ready-badge">
            <Check size={16} /> Processed locally
          </div>
        </div>
        <div className="result-tools">
          <button className="control" onClick={exportTranscript}>
            <Download size={15} /> Export transcript
          </button>
          <button className="control" onClick={addCalendar}>
            <CalendarDays size={15} /> Add to calendar
          </button>
          <button className="control" onClick={share}>
            <Share2 size={15} /> Share
          </button>
        </div>
        {audio && (
          <audio ref={audioRef} className="audio" controls src={audio} />
        )}
        <div className="result-grid">
          <div className="result-main">
            <section className="insight-card summary">
              <div className="section-label">
                <Sparkles size={16} /> AI SUMMARY
              </div>
              <p>
                {i?.summary ||
                  "No summary is available yet. Restart the backend and process this meeting again."}
              </p>
            </section>
            <div className="split">
              <Insight
                title="Key points"
                icon={<Sparkles size={15} />}
                items={i?.key_points || []}
              />
              <Insight
                title="Decisions"
                icon={<Check size={15} />}
                items={i?.decisions || []}
              />
            </div>
            <section className="result-section">
              <div className="section-label">
                <ListChecks size={16} /> ACTION ITEMS{" "}
                <span className="count">{i?.action_items?.length || 0}</span>
              </div>
              {i?.action_items?.length ? (
                <div className="actions">
                  {i.action_items.map((a, n) => (
                    <div className="action" key={n}>
                      <div className="checkbox" />
                      <div>
                        <b>{a.task}</b>
                        <p>
                          {a.owner && `Owner: ${a.owner}`}
                          {a.deadline && ` · Deadline: ${a.deadline}`}
                        </p>
                      </div>
                      <span className={`priority ${a.priority || "medium"}`}>
                        {a.priority || "medium"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">No explicit action items were found.</p>
              )}
            </section>
            <section className="result-section">
              <div className="transcript-heading">
                <div className="section-label">
                  <FileAudio size={16} /> TRANSCRIPT{" "}
                  <span className="muted">click a line to play</span>
                </div>
                {speakers.length > 0 && (
                  <button className="speaker-edit" onClick={() => setEditingSpeakers((value) => !value)}>
                    {editingSpeakers ? "Cancel" : "Rename speakers"}
                  </button>
                )}
              </div>
              {editingSpeakers && (
                <div className="speaker-editor">
                  <p>Correct the labels below. The change applies to every matching transcript segment.</p>
                  {editableSpeakers.map((speaker) => (
                    <label key={speaker}>
                      <span>{speaker}</span>
                      <input value={speakerNames[speaker] || ""} onChange={(event) => setSpeakerNames((current) => ({ ...current, [speaker]: event.target.value }))} placeholder={speaker} />
                    </label>
                  ))}
                  <button className="primary small" disabled={savingSpeakers} onClick={saveSpeakerNames}>
                    {savingSpeakers ? "Saving…" : "Save speaker names"}
                  </button>
                </div>
              )}
              <div className="final-transcript">
                {meeting.transcript?.length ? (
                  meeting.transcript.map((s, n) => (
                    <button
                      className="segment transcript-button"
                      key={n}
                      onClick={() => seek(s.start_time)}
                    >
                      <span className="segment-time">{fmt(s.start_time)}</span>
                      <div>
                        <b>{s.speaker}</b>
                        <p>{s.text}</p>
                      </div>
                    </button>
                  ))
                ) : (
                  <p className="muted">No transcript segments saved.</p>
                )}
              </div>
            </section>
          </div>
          <aside className="ask-card">
            <div className="ask-icon">
              <Sparkles size={17} />
            </div>
            <h3>Ask this meeting</h3>
            <p>Get an answer grounded in this transcript.</p>
            <textarea
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              placeholder="What did we decide about…"
            />
            <button className="primary wide" disabled={asking} onClick={submit}>
              {asking ? "Thinking…" : "Ask question"} <ChevronRight size={16} />
            </button>
            {answer && (
              <div className="answer">
                <b>kushagra.ai intelligence</b>
                <p>{answer}</p>
              </div>
            )}
          </aside>
        </div>
      </div>
    </Shell>
  );
}
function Insight({
  title,
  icon,
  items,
}: {
  title: string;
  icon: React.ReactNode;
  items: string[];
}) {
  return (
    <section className="result-section">
      <div className="section-label">
        {icon} {title.toUpperCase()}
      </div>
      {items.length ? (
        <ul>
          {items.map((x, n) => (
            <li key={n}>{x}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">Nothing explicit was captured.</p>
      )}
    </section>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
