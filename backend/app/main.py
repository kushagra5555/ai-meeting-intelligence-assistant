import json
import os
import base64
import tempfile
import asyncio
import time
import shutil
import sqlite3
import uuid
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA / "meetings.db")))
AUDIO_PATH = Path(os.getenv("AUDIO_STORAGE_PATH", str(DATA / "recordings")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
AUDIO_PATH.mkdir(parents=True, exist_ok=True)
LIVE_CHUNK_SECONDS = 8
IDENTITY_CONFIDENCE_THRESHOLD = float(os.getenv("SPEAKER_IDENTITY_THRESHOLD", "0.82"))

app = FastAPI(title="kushagra.ai API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/audio", StaticFiles(directory=AUDIO_PATH), name="audio")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL, participants TEXT, created_at TEXT NOT NULL, duration INTEGER DEFAULT 0, audio_path TEXT, status TEXT NOT NULL DEFAULT 'draft', speaker_identity_json TEXT DEFAULT '{}', speaker_overrides_json TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS transcript_segments (id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL, start_time REAL, end_time REAL, speaker TEXT, text TEXT NOT NULL, FOREIGN KEY(meeting_id) REFERENCES meetings(id));
        CREATE TABLE IF NOT EXISTS meeting_intelligence (meeting_id TEXT PRIMARY KEY, summary TEXT, key_points_json TEXT, decisions_json TEXT, action_items_json TEXT, FOREIGN KEY(meeting_id) REFERENCES meetings(id));
        """)
        for column in ("speaker_identity_json TEXT DEFAULT '{}'", "speaker_overrides_json TEXT DEFAULT '{}' "):
            try: c.execute(f"ALTER TABLE meetings ADD COLUMN {column}")
            except sqlite3.OperationalError: pass
        # Normalize legacy AssemblyAI temporary labels from recordings created before this fix.
        c.execute("UPDATE transcript_segments SET speaker='Speaker 2' WHERE speaker IN ('Speaker PENDING', 'Speaker UNKNOWN') AND meeting_id IN (SELECT meeting_id FROM transcript_segments WHERE speaker='Speaker 1')")
        c.execute("UPDATE transcript_segments SET speaker='Speaker 1' WHERE speaker IN ('Speaker PENDING', 'Speaker UNKNOWN')")
init_db()

class MeetingCreate(BaseModel):
    title: str
    date: str
    participants: str = ""

class Segment(BaseModel):
    start_time: float = 0
    end_time: float = 0
    speaker: str = "Speaker 1"
    text: str

class SpeakerNames(BaseModel):
    names: dict[str, str]

class AskBody(BaseModel):
    question: str

def meeting_payload(row):
    item = dict(row)
    item["participants"] = item.get("participants") or ""
    item["speaker_identity"] = json.loads(item.get("speaker_identity_json") or "{}")
    item["speaker_overrides"] = json.loads(item.get("speaker_overrides_json") or "{}")
    item["action_items_count"] = 0
    return item

def participant_list(value: str) -> list[str]:
    names = []
    for raw in re.split(r"[,;\n]", value or ""):
        name = raw.strip()
        if name and name.casefold() not in {x.casefold() for x in names}:
            names.append(name)
    return names

@app.get("/api/health")
def health(): return {"ok": True}

@app.websocket("/api/meetings/{meeting_id}/assembly-live")
async def assembly_live_transcription(meeting_id: str, socket: WebSocket, source: str = "mixed"):
    """Proxy a separate microphone or meeting-audio stream to AssemblyAI."""
    await socket.accept()
    key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    if not key:
        await socket.send_json({"type": "error", "message": "AssemblyAI API key is not configured."})
        await socket.close()
        return
    uri = "wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&speech_model=u3-rt-pro&format_turns=true&speaker_labels=true&max_speakers=2"
    started = time.monotonic()
    with db() as c:
        meeting = c.execute("SELECT participants FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    participants = participant_list(meeting["participants"] if meeting else "")
    source_speaker = (participants[0] if source == "mic" and participants else "You") if source == "mic" else (participants[1] if source == "meeting" and len(participants) > 1 else "Participant")
    try:
        async with websockets.connect(uri, additional_headers={"Authorization": key}, max_size=8 * 1024 * 1024) as upstream:
            speaker_aliases: dict[str, str] = {}
            async def receive_transcripts():
                async for raw in upstream:
                    event = json.loads(raw)
                    if event.get("type") == "Error":
                        await socket.send_json({"type": "error", "message": f"AssemblyAI: {event.get('error', 'stream error')}"})
                        continue
                    if event.get("type") != "Turn":
                        continue
                    text_value = (event.get("utterance") or event.get("transcript") or "").strip()
                    if not text_value:
                        continue
                    words = event.get("words") or []
                    start = (words[0].get("start", 0) / 1000) if words else max(0, time.monotonic() - started - 1)
                    end = (words[-1].get("end", 0) / 1000) if words else (time.monotonic() - started)
                    label = str(event.get("speaker_label") or (words[0].get("speaker") if words else None) or "A").strip()
                    if source in ("mic", "meeting"):
                        speaker = source_speaker
                    elif label in ("A", "B"):
                        speaker = {"A": "Speaker 1", "B": "Speaker 2"}[label]
                        speaker_aliases[label] = speaker
                    elif label.upper() in ("UNKNOWN", "PENDING", ""):
                        # AssemblyAI may emit PENDING before a stable label. Keep only two generic channels.
                        speaker = speaker_aliases.setdefault(label.upper() or "UNKNOWN", "Speaker 2" if "Speaker 1" in speaker_aliases.values() else "Speaker 1")
                    else:
                        speaker = speaker_aliases.setdefault(label, f"Speaker {len(set(speaker_aliases.values())) + 1}")
                    item = {"start_time": round(start, 2), "end_time": round(end, 2), "speaker": speaker, "text": text_value}
                    if event.get("end_of_turn"):
                        with db() as c:
                            c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, item["start_time"], item["end_time"], item["speaker"], item["text"]))
                        await socket.send_json({"type": "final", **item})
                    else:
                        await socket.send_json({"type": "interim", "start_time": item["start_time"], "text": text_value})
            receiver = asyncio.create_task(receive_transcripts())
            try:
                while True:
                    message = await socket.receive()
                    if message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
                    elif message.get("type") == "websocket.disconnect":
                        break
            except WebSocketDisconnect:
                pass
            finally:
                try: await upstream.send(json.dumps({"type": "Terminate"}))
                except Exception: pass
                receiver.cancel()
    except Exception as exc:
        try: await socket.send_json({"type": "error", "message": f"AssemblyAI live transcription failed: {str(exc)[:160]}"})
        except Exception: pass

@app.websocket("/api/meetings/{meeting_id}/live")
async def live_transcription(meeting_id: str, socket: WebSocket):
    """Proxy browser PCM to Gemini Live without exposing the API key."""
    await socket.accept()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        await socket.send_json({"type": "error", "message": "Gemini API key is not configured."})
        await socket.close()
        return
    uri = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    started = time.monotonic()
    try:
        async with websockets.connect(uri, additional_headers={"x-goog-api-key": key}, max_size=8 * 1024 * 1024) as upstream:
            await upstream.send(json.dumps({"setup": {"model": "models/gemini-3.5-transcribe-live", "generationConfig": {"responseModalities": ["TEXT"]}, "inputAudioTranscription": {"languageCodes": [], "mode": "SMART"}}}))
            async def receive_gemini():
                async for raw in upstream:
                    event = json.loads(raw)
                    content = event.get("serverContent") or {}
                    interim = (content.get("interimInputTranscription") or {}).get("text")
                    final = (content.get("inputTranscription") or {}).get("text")
                    if interim: await socket.send_json({"type": "interim", "text": interim})
                    if final:
                        now = round(time.monotonic() - started, 2)
                        item = {"type": "final", "start_time": max(0, now - 1), "end_time": now, "speaker": "Speaker", "text": final}
                        with db() as c: c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, item["start_time"], item["end_time"], item["speaker"], item["text"]))
                        await socket.send_json(item)
            receiver = asyncio.create_task(receive_gemini())
            try:
                while True:
                    chunk = await socket.receive_bytes()
                    await upstream.send(json.dumps({"realtimeInput": {"audio": {"data": base64.b64encode(chunk).decode("ascii"), "mimeType": "audio/pcm;rate=16000"}}}))
            except WebSocketDisconnect:
                pass
            finally:
                receiver.cancel()
    except Exception:
        try: await socket.send_json({"type": "error", "message": "Live transcription connection failed. A final transcript will still be generated after recording."})
        except Exception: pass

@app.post("/api/meetings")
def create_meeting(body: MeetingCreate):
    meeting_id = str(uuid.uuid4())
    with db() as c:
        c.execute("INSERT INTO meetings (id,title,date,participants,created_at,status) VALUES (?,?,?,?,?,?)", (meeting_id, body.title, body.date, body.participants, datetime.now(timezone.utc).isoformat(), "ready"))
    return {"id": meeting_id}

@app.get("/api/meetings")
def list_meetings():
    with db() as c:
        rows = c.execute("SELECT m.*, (SELECT COUNT(*) FROM transcript_segments t WHERE t.meeting_id=m.id) AS segment_count FROM meetings m ORDER BY date DESC, created_at DESC").fetchall()
        result = [meeting_payload(r) for r in rows]
        for item in result:
            intel = c.execute("SELECT action_items_json FROM meeting_intelligence WHERE meeting_id=?", (item["id"],)).fetchone()
            if intel: item["action_items_count"] = len(json.loads(intel[0] or "[]"))
        return result

@app.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str):
    with db() as c:
        row = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row: raise HTTPException(404, "Meeting not found")
        item = meeting_payload(row)
        item["transcript"] = [dict(x) for x in c.execute("SELECT * FROM transcript_segments WHERE meeting_id=? ORDER BY start_time, id", (meeting_id,)).fetchall()]
        intel = c.execute("SELECT * FROM meeting_intelligence WHERE meeting_id=?", (meeting_id,)).fetchone()
        item["intelligence"] = None if not intel else {"summary": intel["summary"], "key_points": json.loads(intel["key_points_json"]), "decisions": json.loads(intel["decisions_json"]), "action_items": json.loads(intel["action_items_json"])}
        return item

@app.post("/api/meetings/{meeting_id}/transcript")
def add_segment(meeting_id: str, segment: Segment):
    with db() as c:
        c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, segment.start_time, segment.end_time, segment.speaker, segment.text))
    return {"ok": True}

@app.patch("/api/meetings/{meeting_id}/speakers")
def rename_speakers(meeting_id: str, body: SpeakerNames):
    """Persist manual corrections; these always override automatic identity resolution."""
    cleaned = {str(old).strip(): str(new).strip() for old, new in body.names.items() if str(old).strip() and str(new).strip()}
    with db() as c:
        row = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meeting not found")
        identity = json.loads(row["speaker_identity_json"] or "{}")
        overrides = json.loads(row["speaker_overrides_json"] or "{}")
        for old, new in cleaned.items():
            source = old
            if old not in identity:
                source = next((key for key, value in identity.items() if value.get("participant_name") == old), old)
            current_name = identity.get(source, {}).get("participant_name") or source
            c.execute("UPDATE transcript_segments SET speaker=? WHERE meeting_id=? AND speaker=?", (new, meeting_id, current_name))
            c.execute("UPDATE transcript_segments SET speaker=? WHERE meeting_id=? AND speaker=?", (new, meeting_id, source))
            overrides[source] = new
            identity[source] = {"participant_name": new, "confidence": 1.0, "evidence": "Manual user correction."}
        c.execute("UPDATE meetings SET speaker_identity_json=?, speaker_overrides_json=? WHERE id=?", (json.dumps(identity), json.dumps(overrides), meeting_id))
    return {"ok": True, "names": cleaned, "speaker_identity": identity}

@app.post("/api/meetings/{meeting_id}/recording")
async def upload_recording(meeting_id: str, file: UploadFile = File(...), duration: int = 0):
    suffix = Path(file.filename or "recording.webm").suffix or ".webm"
    name = f"{meeting_id}{suffix}"
    destination = AUDIO_PATH / name
    with destination.open("wb") as out: shutil.copyfileobj(file.file, out)
    with db() as c: c.execute("UPDATE meetings SET audio_path=?, duration=?, status='processing' WHERE id=?", (name, duration, meeting_id))
    return {"audio_url": f"/audio/{name}"}

@app.post("/api/meetings/{meeting_id}/recording/chunk")
async def transcribe_chunk(meeting_id: str, file: UploadFile = File(...), start_time: float = 0):
    """Near-real-time chunk transcription for the live recording view."""
    if not os.getenv("GEMINI_API_KEY", "").strip(): return {"segments": []}
    raw = await file.read()
    if not raw: return {"segments": []}
    temp_path = Path(tempfile.gettempdir()) / f"meeting-chunk-{uuid.uuid4()}.webm"
    try:
        temp_path.write_bytes(raw)
        transcript = await transcribe_gemini_audio(temp_path)
        segments = []
        with db() as c:
            if transcript:
                item = {"start_time": start_time, "end_time": start_time + LIVE_CHUNK_SECONDS, "speaker": "Speaker 1", "text": transcript}
                c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, item["start_time"], item["end_time"], item["speaker"], item["text"]))
                segments.append(item)
        return {"segments": segments}
    except httpx.HTTPStatusError as exc:
        return {"segments": [], "error": f"Gemini transcription returned HTTP {exc.response.status_code}.", "retryable": exc.response.status_code == 429}
    except Exception as exc:
        return {"segments": [], "error": f"Live audio processing failed: {str(exc)[:180]}"}
    finally:
        temp_path.unlink(missing_ok=True)

def transcript_text(meeting_id):
    with db() as c: return "\n".join(f"{x['speaker']}: {x['text']}" for x in c.execute("SELECT * FROM transcript_segments WHERE meeting_id=? ORDER BY start_time,id", (meeting_id,)).fetchall())

def infer_spoken_speaker_names(meeting_id: str) -> dict[str, str]:
    """Use explicit self-introductions to replace generic diarization labels."""
    patterns = [
        re.compile(r"\b(?:i am|i'm|my name is|this is)\s+([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,2})", re.I),
        re.compile(r"\bmera naam\s+([A-Za-z.'-]+(?:\s+[A-Za-z.'-]+){0,2})\s+hai\b", re.I),
    ]
    mapping: dict[str, str] = {}
    with db() as c:
        rows = c.execute("SELECT speaker,text FROM transcript_segments WHERE meeting_id=? ORDER BY start_time,id", (meeting_id,)).fetchall()
        for row in rows:
            speaker = str(row["speaker"] or "").strip()
            if not speaker.lower().startswith("speaker"):
                continue
            for pattern in patterns:
                match = pattern.search(str(row["text"] or ""))
                if match:
                    stop_words = {"and", "but", "from", "to", "is", "are", "will", "can", "today", "here", "going", "joining"}
                    tokens = match.group(1).strip().split()
                    tokens = tokens[: next((i for i, token in enumerate(tokens) if token.lower().strip(".,!?\"") in stop_words), len(tokens))]
                    name = " ".join(tokens).strip(" .,!?\"")
                    if name and name.lower() not in stop_words and 1 < len(name) <= 60:
                        mapping[speaker] = name
                        break
        for old, new in mapping.items():
            c.execute("UPDATE transcript_segments SET speaker=? WHERE meeting_id=? AND speaker=?", (new, meeting_id, old))
    return mapping

def apply_speaker_mapping(meeting_id: str, mapping: dict[str, str]) -> None:
    with db() as c:
        for old, new in mapping.items():
            if old and new and old != new:
                c.execute("UPDATE transcript_segments SET speaker=? WHERE meeting_id=? AND speaker=?", (new, meeting_id, old))

def fallback_contextual_identity(participants: list[str], transcript: str) -> dict[str, dict[str, Any]]:
    """Conservative offline fallback for reciprocal names when Gemini is unavailable."""
    if len(participants) != 2:
        return {}
    speaker_lines: dict[str, list[str]] = {}
    for line in transcript.splitlines():
        if ":" in line:
            speaker, text = line.split(":", 1)
            speaker_lines.setdefault(speaker.strip(), []).append(text.strip())
    mentions: dict[str, dict[str, float]] = {}
    for speaker, lines in speaker_lines.items():
        joined = " ".join(lines).casefold()
        mentions[speaker] = {}
        for participant in participants:
            best = 0.0
            candidate_tokens = re.findall(r"[\w'-]+", joined)
            for token in candidate_tokens:
                best = max(best, SequenceMatcher(None, token.casefold(), participant.casefold()).ratio())
            if participant.casefold() in joined:
                best = 1.0
            if best >= 0.60:
                mentions[speaker][participant] = best
    speakers = list(mentions)
    if len(speakers) != 2:
        return {}
    first, second = speakers
    first_names = {max(mentions[first], key=mentions[first].get)} if mentions[first] else set()
    second_names = {max(mentions[second], key=mentions[second].get)} if mentions[second] else set()
    if len(first_names) != 1 or len(second_names) != 1 or first_names == second_names:
        return {}
    first_addressed = next(iter(first_names))
    second_addressed = next(iter(second_names))
    return {
        first: {"participant_name": second_addressed, "confidence": 0.84, "evidence": f"{first} addressed {first_addressed}; reciprocal name evidence assigned the other participant."},
        second: {"participant_name": first_addressed, "confidence": 0.84, "evidence": f"{second} addressed {second_addressed}; reciprocal name evidence assigned the other participant."},
    }

async def resolve_speaker_identity(participants: list[str], transcript: str) -> dict[str, dict[str, Any]]:
    """Resolve generic speaker IDs from transcript context only; no voice biometrics."""
    if not participants or not os.getenv("GEMINI_API_KEY", "").strip():
        return {}
    participant_text = "\n".join(f"- {name}" for name in participants)
    prompt = f'''You are resolving speaker identities in a meeting transcript.
Known meeting participants:
{participant_text}

Determine whether each anonymous speaker can be mapped to a known participant using explicit conversational evidence.
Use evidence such as a self-introduction, a direct name exchange, or a clear reciprocal address.
Do not assume that a person mentioned by name is the speaker. Do not use voice, gender, accent, or outside knowledge. Do not invent participants.
Only return participant names exactly as they appear in the known participant list. If evidence is insufficient, return null and confidence 0.

Return ONLY this JSON:
{{"speaker_mapping":[{{"speaker_id":"Speaker 1","participant_name":null,"confidence":0,"evidence":"Insufficient evidence."}}]}}

Transcript:
{transcript}'''
    try:
        result = await call_gemini(prompt, schema_hint_override='{"speaker_mapping":[{"speaker_id":"Speaker 1","participant_name":null,"confidence":0,"evidence":"Insufficient evidence."}]}')
        known = {name.casefold(): name for name in participants}
        speaker_ids = {line.split(":", 1)[0].strip() for line in transcript.splitlines() if ":" in line}
        resolved: dict[str, dict[str, Any]] = {}
        for item in result.get("speaker_mapping", []):
            if not isinstance(item, dict):
                continue
            speaker = str(item.get("speaker_id") or "").strip()
            raw_name = str(item.get("participant_name") or "").strip()
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
            except (TypeError, ValueError):
                confidence = 0.0
            canonical_name = known.get(raw_name.casefold()) if raw_name else None
            if speaker in speaker_ids and speaker.lower().startswith("speaker"):
                resolved[speaker] = {
                    "participant_name": canonical_name if confidence >= IDENTITY_CONFIDENCE_THRESHOLD else None,
                    "confidence": confidence,
                    "evidence": str(item.get("evidence") or "Insufficient evidence.")[:500],
                }
        return resolved
    except Exception:
        return fallback_contextual_identity(participants, transcript)

def whisper_transcribe(meeting_id: str):
    """Best-effort CPU transcription. The optional dependency keeps basic installs lightweight."""
    try:
        from faster_whisper import WhisperModel
        with db() as c: row = c.execute("SELECT audio_path FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row or not row["audio_path"]: return ""
        model = WhisperModel(os.getenv("STT_MODEL", "base"), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(AUDIO_PATH / row["audio_path"]), vad_filter=True)
        text_segments = list(segments)
        with db() as c:
            for segment in text_segments:
                c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, segment.start, segment.end, "Speaker 1", segment.text.strip()))
        return transcript_text(meeting_id)
    except Exception:
        return ""

def fallback_intelligence(text):
    rows = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if ":" in raw:
            speaker, sentence = raw.split(":", 1)
        else:
            speaker, sentence = "Unknown speaker", raw
        sentence = sentence.strip()
        if sentence:
            rows.append((speaker.strip(), sentence))
    lines = [sentence for _, sentence in rows]
    decision_terms = ("we decided", "decision is", "agreed to", "let's go with", "we will use", "final decision", "we are going to")
    action_terms = ("i will", "i'll", "i can", "i need to", "we need to", "please send", "please review", "should build", "should prepare", "can show", "will prepare", "will build")
    decisions = [sentence for _, sentence in rows if any(term in sentence.casefold() for term in decision_terms)]
    action_items = []
    for speaker, sentence in rows:
        lower = sentence.casefold()
        if any(term in lower for term in action_terms):
            task = re.sub(r"^(yes,?\s*)?(i('| a)?m|we|please)\s+", "", sentence, flags=re.I).strip()
            action_items.append({"task": task.rstrip(".!?"), "owner": speaker or None, "deadline": None, "priority": "medium"})
    unique_actions = []
    seen = set()
    for item in action_items:
        key = item["task"].casefold()
        if key not in seen:
            seen.add(key)
            unique_actions.append(item)
    summary = " ".join(lines[:2]) if lines else "Meeting transcript captured successfully."
    return {"summary": summary, "key_points": lines[:5], "decisions": decisions[:5], "action_items": unique_actions[:10]}

def parse_json_response(content: str) -> dict[str, Any]:
    content = content[content.find("{"):content.rfind("}") + 1]
    return json.loads(content)

async def call_gemini(prompt: str, audio_path: Path | None = None, model_override: str | None = None, schema_hint_override: str | None = None) -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY is not configured")
    model = model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    schema_hint = schema_hint_override or '{"transcript_segments":[{"start_time":0,"end_time":0,"speaker":"Speaker 1","text":"..."}],"summary":"...","key_points":["..."],"decisions":["..."],"action_items":[{"task":"...","owner":null,"deadline":null,"priority":"medium"}],"speaker_mapping":[{"speaker_id":"Speaker 1","participant_name":null,"confidence":0,"evidence":""}]}'
    prompt_text = f"""You are analyzing one private meeting. Return ONLY valid JSON matching this shape: {schema_hint}
If audio is attached, transcribe EVERY spoken sentence from the beginning to the end of the recording. Do not return only a summary or only the final sentence. Keep all meaningful speech, in chronological order, with approximate timestamps. Use only facts present in the meeting. Do not invent names, owners, dates, decisions, or tasks. If unsupported, use null or an empty array. {prompt}"""
    parts: list[dict[str, Any]] = [{"text": prompt_text}]
    if audio_path:
        raw = audio_path.read_bytes()
        parts.insert(0, {"inline_data": {"mime_type": "audio/webm", "data": base64.b64encode(raw).decode("ascii")}})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers={"x-goog-api-key": key}, json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}})
        response.raise_for_status()
        content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    parsed = parse_json_response(content)
    return {"transcript_segments": parsed.get("transcript_segments", []), "summary": str(parsed.get("summary", "")), "key_points": parsed.get("key_points", []), "decisions": parsed.get("decisions", []), "action_items": parsed.get("action_items", [])}

async def transcribe_gemini_audio(audio_path: Path, detailed: bool = False) -> str | dict[str, Any]:
    """Use Gemini's Transcribe Interactions API, not a general chat completion."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY is not configured")
    model = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-transcribe")
    raw = audio_path.read_bytes()
    mime_type = "audio/webm"
    headers = {"x-goog-api-key": key}
    async with httpx.AsyncClient(timeout=120) as client:
        start_upload = await client.post(
            "https://generativelanguage.googleapis.com/upload/v1beta/files",
            headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": str(len(raw)), "X-Goog-Upload-Header-Content-Type": mime_type, "Content-Type": "application/json"},
            json={"file": {"display_name": audio_path.name}},
        )
        start_upload.raise_for_status()
        upload_url = start_upload.headers.get("x-goog-upload-url")
        if not upload_url: raise RuntimeError("Gemini did not return an upload URL")
        uploaded = await client.post(upload_url, headers={"X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0", "Content-Type": mime_type}, content=raw)
        uploaded.raise_for_status()
        remote_file = uploaded.json().get("file", {})
        uri, name = remote_file.get("uri"), remote_file.get("name")
        if not uri: raise RuntimeError("Gemini did not return an uploaded audio URI")
        try:
            # Audio files can be briefly PROCESSING after upload.  Sending the
            # interaction too early produces an empty transcript.
            for _ in range(30):
                status = await client.get(f"https://generativelanguage.googleapis.com/v1beta/{name}", headers=headers)
                status.raise_for_status()
                remote_file = status.json()
                state = (remote_file.get("state") or "ACTIVE").upper()
                if state == "ACTIVE":
                    uri = remote_file.get("uri", uri)
                    break
                if state == "FAILED": raise RuntimeError("Gemini could not process the uploaded audio")
                await asyncio.sleep(1)
            else: raise RuntimeError("Gemini audio preparation timed out")
            transcription_config = {"language_codes": [], "mode": {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}} if detailed else {"language_codes": [], "mode": "smart"}
            interaction = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={**headers, "Content-Type": "application/json"},
                json={"model": model, "input": [{"type": "audio", "uri": uri, "mime_type": mime_type}], "generation_config": {"transcription_config": transcription_config}},
            )
            interaction.raise_for_status()
            result = interaction.json()
            text = result.get("output_text") or result.get("outputText") or ""
            if not text:
                text = "\n".join(
                    content.get("text", "")
                    for step in result.get("steps", [])
                    for content in step.get("content", [])
                    if content.get("type") == "text"
                )
            if not detailed:
                return text.strip()
            detailed_segments = []
            for step in result.get("steps", []):
                for content in step.get("content", []):
                    words = [a for a in content.get("annotations", []) if a.get("type") == "word_info"]
                    current = None
                    for word in words:
                        raw_speaker = word.get("speaker") or "spk_1"
                        speaker = f"Speaker {raw_speaker.split('_', 1)[1]}" if raw_speaker.startswith("spk_") else raw_speaker
                        start_match = re.search(r"[0-9.]+", str(word.get("start_offset", "0")))
                        end_match = re.search(r"[0-9.]+", str(word.get("end_offset", "0")))
                        start = float(start_match.group()) if start_match else 0.0
                        end = float(end_match.group()) if end_match else start
                        if current and current["speaker"] == speaker and start - current["end_time"] < 1.5:
                            current["text"] += " " + word.get("text", "")
                            current["end_time"] = end
                        else:
                            current = {"start_time": start, "end_time": end, "speaker": speaker, "text": word.get("text", "")}
                            detailed_segments.append(current)
            return {"text": text.strip(), "segments": detailed_segments}
        finally:
            if name:
                await client.delete(f"https://generativelanguage.googleapis.com/v1beta/{name}", headers=headers)

async def call_llm(prompt: str) -> dict[str, Any]:
    if os.getenv("GEMINI_API_KEY", "").strip():
        configured = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        candidates = list(dict.fromkeys([configured, "gemini-3.5-flash", "gemini-2.5-flash"]))
        last_error = None
        for model in candidates:
            try:
                return await call_gemini(prompt, model_override=model)
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1)
        raise RuntimeError(f"Gemini analysis unavailable after retries: {type(last_error).__name__}")
    base = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
    model = os.getenv("LM_STUDIO_MODEL", "local-model")
    system = "Return ONLY valid JSON with summary (string), key_points (string[]), decisions (string[]), action_items ({task,owner,deadline,priority}[]). Never invent facts; use null for unsupported owner/deadline."
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{base}/chat/completions", json={"model": model, "temperature": 0.1, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    content = content[content.find("{"):content.rfind("}")+1]
    parsed = json.loads(content)
    return {"summary": str(parsed.get("summary", "")), "key_points": parsed.get("key_points", []), "decisions": parsed.get("decisions", []), "action_items": parsed.get("action_items", [])}

@app.post("/api/meetings/{meeting_id}/process")
async def process(meeting_id: str):
    text = transcript_text(meeting_id)
    with db() as c:
        meeting_row = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if not meeting_row:
        raise HTTPException(404, "Meeting not found")
    participants = participant_list(meeting_row["participants"] or "")
    manual_overrides = json.loads(meeting_row["speaker_overrides_json"] or "{}")
    if os.getenv("GEMINI_API_KEY", "").strip():
        row = meeting_row
        audio = AUDIO_PATH / row["audio_path"] if row and row["audio_path"] else None
        with db() as c:
            existing_speakers = {str(x[0]) for x in c.execute("SELECT DISTINCT speaker FROM transcript_segments WHERE meeting_id=?", (meeting_id,)).fetchall()}
        source_transcript_available = bool(set(participants) & existing_speakers)
        if audio and audio.exists() and not source_transcript_available:
            try:
                full_transcript = await transcribe_gemini_audio(audio, detailed=True)
                with db() as c:
                    c.execute("DELETE FROM transcript_segments WHERE meeting_id=?", (meeting_id,))
                    if isinstance(full_transcript, dict) and full_transcript.get("segments"):
                        for segment in full_transcript["segments"]:
                            c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, segment["start_time"], segment["end_time"], segment["speaker"], segment["text"].strip()))
                    elif full_transcript:
                        c.execute("INSERT INTO transcript_segments (meeting_id,start_time,end_time,speaker,text) VALUES (?,?,?,?,?)", (meeting_id, 0, 0, "Speaker 1", full_transcript if isinstance(full_transcript, str) else full_transcript.get("text", "")))
                text = transcript_text(meeting_id)
            except Exception:
                pass
    if not text: text = whisper_transcribe(meeting_id)
    if not text: raise HTTPException(400, "No transcript was captured")
    identity = await resolve_speaker_identity(participants, text)
    automatic_mapping = {speaker: info["participant_name"] for speaker, info in identity.items() if info.get("participant_name") and speaker not in manual_overrides}
    apply_speaker_mapping(meeting_id, automatic_mapping)
    for source, override in manual_overrides.items():
        resolved_name = identity.get(source, {}).get("participant_name") or source
        apply_speaker_mapping(meeting_id, {resolved_name: override, source: override})
        identity[source] = {"participant_name": override, "confidence": 1.0, "evidence": "Manual user correction."}
    text = transcript_text(meeting_id)
    with db() as c:
        c.execute("UPDATE meetings SET speaker_identity_json=? WHERE id=?", (json.dumps(identity), meeting_id))
    try: intelligence = await call_llm(f"Analyze this meeting transcript factually. Preserve the identified speaker names when discussing who said what. Do not invent names or identities.\n\n{text}")
    except Exception: intelligence = fallback_intelligence(text)
    with db() as c:
        c.execute("INSERT OR REPLACE INTO meeting_intelligence VALUES (?,?,?,?,?)", (meeting_id, intelligence["summary"], json.dumps(intelligence["key_points"]), json.dumps(intelligence["decisions"]), json.dumps(intelligence["action_items"])))
        c.execute("UPDATE meetings SET status='ready' WHERE id=?", (meeting_id,))
    return intelligence

@app.post("/api/meetings/{meeting_id}/ask")
async def ask(meeting_id: str, body: AskBody):
    text = transcript_text(meeting_id)
    if not text: raise HTTPException(400, "This meeting has no transcript")
    try:
        answer = await call_llm(f"Answer the question using ONLY this transcript. If unsupported, say you cannot find it in the transcript.\nQuestion: {body.question}\nTranscript:\n{text}")
        return {"answer": answer["summary"]}
    except Exception:
        return {"answer": "Gemini analysis is temporarily unavailable. Please try this question again in a moment."}
