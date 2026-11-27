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
6. Desktop er **Mira** icon e double click koro (ba `app.bat`). Nijer window e app khulbe.
7. Ba shudhu bolo **"Hey Mira"**. Window khule shunte shuru korbe, tarpor kaj bolo.

`setup.bat` nijei Desktop icon banay, Windows chalu holei "Hey Mira" shona chalu kore,
ar wake word er chhoto model (~40 MB) download kore. Pore abar korte:
`.venv\Scripts\python main.py --install`

Offline backup ar private mode er jonno (optional):

```powershell
winget install --id Ollama.Ollama
ollama pull gemma4:e2b
```

## App

| Button | Ki hoy |
| --- | --- |
| Boro mic | Kotha bolo. Chup korle nije thame. Abar chaple sathe sathe shesh |
| Mira bolar shomoy mic | Thamiye tomar kotha shune |
| একটানা কথা | Uttor er por nije abar shune (call er moto) |
| থামাও / Esc | Sob thamao |
| Chobi / Ctrl+V / drag | Chobi theke prosno ba math |
| Screen | 3 second por screen dekhe uttor |
| Tala (lock) | Private mode |
| Ctrl+Space | Mic |

Shutdown, restart, website kholar age window e **হ্যাঁ, করো** button chapte hoy.
Voice diye eta approve kora jay na.

"Hey Mira" bondho korte `.env` e `WAKE_WORD=off`, ar Windows start theke bad dite:
`.venv\Scripts\python main.py --no-startup`

## Terminal command (`start.bat`)

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
- "Hey Mira" shona pura offline (Vosk). Wake word er age kono audio PC theke baire jay na.
  "Hey Mira" er porer kotha Groq e jay, jemon mic button e.
- App shudhu ei PC theke khola jay (`127.0.0.1`), onno website ba network theke na.
- `.env` (API key) ar `data/` folder (memory, note) git e jay na. Egulo kokhono upload koro na.
- Shutdown, restart ar website link khulte terminal e `yes` likhte hoy, app e button chapte hoy.

## Code

| File | Kaj |
| --- | --- |
| `main.py` | Chalu korar file |
| `agent/web.py` | Window app er server (shudhu 127.0.0.1) |
| `agent/static/index.html` | App er screen |
| `agent/wake.py` | "Hey Mira" offline wake word |
| `agent/shortcut.py` | Desktop icon ar Windows start |
| `agent/cli.py` | Terminal chat loop ar command |
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
- [x] Phase 3a: window app, "Hey Mira" wake word, Windows start e chalu
- [ ] Phase 3b: tray icon, offline voice input
- [ ] Phase 4: PDF study helper, daily briefing, clipboard translate, file organizer
