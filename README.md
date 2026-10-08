# AI Meeting Intelligence Assistant

A local-first meeting assistant prototype built with React, TypeScript, FastAPI, SQLite, browser audio capture, Gemini, and optional Whisper transcription.

It records a meeting in the browser, preserves the recording locally, shows live captions, produces a timestamped transcript, and generates structured meeting intelligence such as summaries, decisions, and action items.

## What this demonstrates

- Full-stack product development with a React/Vite frontend and FastAPI backend
- Browser microphone and shared-tab audio capture
- WebSocket-based live meeting updates
- Local SQLite persistence and audio playback
- AI-assisted summaries, decisions, action items, and meeting Q&A
- A privacy-first prototype design that keeps recordings local by default

## Architecture

```text
Browser microphone / shared-tab audio
              |
              v
        React + Vite UI
              |
              v
        FastAPI REST/WebSocket API
          |                 |
          v                 v
   SQLite + local audio   Gemini / LM Studio
          |
          v
   Transcript + insights
```

## Run locally on Windows

### 1. Configure the backend

From the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Keep the backend terminal running.

### 2. Start the frontend

Open a second terminal in the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

### 3. Enable an AI provider

Copy `.env.example` to `.env`, then configure one of these options:

- **Gemini:** set `GEMINI_API_KEY` and the supported `GEMINI_MODEL`.
- **LM Studio:** load a local instruct model and start its OpenAI-compatible server on port `1234`.

Never commit `.env` or share an API key.

## Testing

The repository includes a GitHub Actions workflow that checks Python syntax and builds the frontend. Run the same local frontend check with:

```powershell
cd frontend
npm run build
```

## Current limitations

- Speaker labels are prototype labels; reliable multi-speaker diarization still needs a dedicated diarization service or model.
- Live captions depend on browser speech-recognition support and may differ from the final transcript.
- Audio and SQLite data are local development data and are intentionally ignored by Git.
- The prototype is not a replacement for consent, privacy, or recording policies in real meetings.

## Privacy and security

Record only with participant consent. Keep API keys server-side in `.env`. Local recordings and the SQLite database are excluded from version control. If Gemini is enabled, audio or transcript data sent to the provider is subject to that provider's terms and account settings.

## Roadmap

- Add production-grade speaker diarization and speaker-name correction
- Add transcript search, export, and synchronized audio navigation
- Add evaluation fixtures for transcription and meeting intelligence quality
- Add authentication and encrypted storage for a production deployment

## License

MIT. See [LICENSE](LICENSE).
