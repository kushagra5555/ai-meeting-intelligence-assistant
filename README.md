# kushagra.ai

A local-first AI meeting assistant prototype. Record real microphone audio in the browser, see live captions, save meetings to SQLite, and generate structured meeting intelligence through Gemini Flash or a local LM Studio model.

## Features

- Real browser microphone recording with pause/resume/stop and audio playback
- Live transcript via browser Web Speech API when supported
- Final transcript via `faster-whisper` when installed, with a safe browser-caption fallback
- SQLite meeting history and local recording storage
- Structured summary, key points, decisions, and action items from Gemini Flash or LM Studio
- Meeting-scoped Q&A grounded in the selected transcript
- Responsive dark product UI with recording, processing, empty, and error states

## Local setup on Windows

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Backend:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --reload
```

3. Frontend in a second terminal:

```powershell
npm install
npm run dev
```

4. Open the Vite URL, usually `http://localhost:5173`.

## LM Studio

Install LM Studio, download a small instruct model suitable for a CPU laptop, load it, and start the local server on port `1234`. Set `LM_STUDIO_MODEL` to the loaded model identifier. The app remains usable if LM Studio is unavailable, but processing will show a helpful error and preserve the transcript.

## Gemini Flash

Alternatively, set `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.1-flash-lite` in `.env`. Gemini is then used to recover a transcript from saved audio and generate meeting intelligence. Keep the key server-side and never commit `.env`.

## STT

The default `STT_MODEL=base` is a practical CPU starting point. `faster-whisper` downloads the model on first use and can be changed to `tiny` for faster testing or `small` for better quality. If it is unavailable, the backend preserves live browser captions as the final transcript so the prototype remains demonstrable.

## Known limitations

Speaker labels are browser-caption placeholders, not diarization. Live caption support depends on browser Web Speech API availability. Audio chunk transcription is intentionally lightweight; final Whisper processing is the accuracy path. LM Studio must be running for AI-generated intelligence and Q&A.

## GitHub commands

```powershell
git init
git add .
git commit -m "Build local meeting intelligence prototype"
git branch -M main
git remote add origin https://github.com/YOUR-USER/YOUR-REPO.git
git push -u origin main
```
