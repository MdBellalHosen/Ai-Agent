# AI Agent: Bangla + English voice assistant (Windows 11)

Female voice e Bangla ar English e kotha bole, math solve kore, chobi ar screen bojhe,
PC control kore, note ar reminder rakhe. Free tier diye chole.

Default nam **Mira** (`.env` file e `AGENT_NAME` bodle nao).

## Setup

1. Python 3.12 install koro (PowerShell):
   ```powershell
   winget install --id Python.Python.3.12
   ```
2. Ei repo download koro: sobuj **Code** button > **Download ZIP**, tarpor unzip.
3. `setup.bat` double click koro. Eta library install kore `.env` file khulbe.
4. Free API key nao ar `.env` e boshao:
   - [Gemini key](https://aistudio.google.com/apikey) (chat, math, chobi)
   - [Groq key](https://console.groq.com/keys) (voice input, backup brain)
5. `check.bat` chalao. Kon ongsho kaj korche ta `OK` ba `FAIL` dekhabe.
6. `start.bat` chalao.

Offline backup ar private mode er jonno (optional):

```powershell
winget install --id Ollama.Ollama
ollama pull gemma4:e2b
```

## Command

| Command | Ki hoy |
| --- | --- |
| Khali Enter | Mic on, kotha shesh hole abar Enter |
| `/bn`, `/en`, `/auto` | Mic er vasha (shuru te Bangla) |
| `/image C:\path\math.jpg \| eta solve koro` | Chobi theke uttor |
| `/screen eta ki error?` | Screen dekhe uttor |
| `/private` | Private mode on/off |
| `/mute` | Voice on/off |
| `/exit` | Bondho |

## Privacy

- Normal mode e lekha, mone rakha kotha, mic er audio, chobi cloud service e jay
  (Gemini, Groq, ar voice er jonno Microsoft). Gemini free tier er data Google tader
  product unnoti te use korte pare.
- `/private` mode e shudhu local Ollama cholbe: likhe chat, tool ar voice bondho.
- `.env` (API key) ar `data/` folder (memory, note) git e jay na. Egulo kokhono upload koro na.
- Shutdown, restart ar website link khulte keyboard e `yes` likhte hoy.

## Code

| File | Kaj |
| --- | --- |
| `main.py` | Chalu korar file |
| `agent/cli.py` | Chat loop ar command |
| `agent/brain.py` | AI model, instruction, tool chalano |
| `agent/tools.py` | PC control feature |
| `agent/voice.py` | Female voice ar mic |
| `agent/vision.py` | Chobi ar screen |
| `agent/memory.py` | Memory ar note |
| `agent/calculator.py` | Safe calculator |
| `agent/check.py` | Setup test |
| `agent/config.py` | `.env` settings |

Notun feature: `agent/tools.py` e function likhe `TOOL_LIST` e ek line add koro.

Test chalate: `.venv\Scripts\python -m unittest`

## Roadmap

- [x] Phase 1: chat, voice, PC control, chobi, note, reminder, private mode
- [ ] Phase 2: nijer app list, `sympy` diye math jachai
- [ ] Phase 3: window app (tray icon), wake word, offline voice input
- [ ] Phase 4: PDF study helper, daily briefing, clipboard translate, file organizer
