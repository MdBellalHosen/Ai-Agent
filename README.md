# Mira: Bangla + English AI assistant (Windows 11)

Desktop app hishebe chole. **"Hey Mira"** bolle nije khule shune, female voice e Bangla ar
English e uttor dey, PC er app khole, math solve kore ar uttor jachai kore, chobi ar screen
bojhe, note ar reminder rakhe. Sob free tier diye chole.

Default nam **Mira** (`.env` file e `AGENT_NAME` bodle nao).

## Setup

1. Python 3.12 install koro (PowerShell):
   ```powershell
   winget install --id Python.Python.3.12
   ```
2. Ei repo download koro: sobuj **Code** button > **Download ZIP**, tarpor unzip.
   (Ba `git clone https://github.com/MdBellalHosen/Ai-Agent.git`)
3. `setup.bat` double click koro. Eta:
   - library install kore,
   - "Hey Mira" er chhoto offline model (~40 MB) namay,
   - Desktop e **Mira** icon banay, ar Windows chalu holei Mira ke background e chalu kore,
   - sesh e `.env` file khule.
4. Free API key nao ar `.env` e boshao, save koro:
   - [Gemini key](https://aistudio.google.com/apikey): chat, math, chobi, Bangla voice
   - [Groq key](https://console.groq.com/keys): backup voice ar backup brain
5. `check.bat` chalao. Kon ongsho kaj korche ta `OK` ba `FAIL` dekhabe.
6. Desktop er **Mira** icon e double click koro, ba shudhu bolo **"Hey Mira"**.

Notun version anle:

```powershell
git pull
.\setup.bat
```

Offline backup ar private mode er jonno (optional, 8 GB RAM e `gemma3:1b` bhalo):

```powershell
winget install --id Ollama.Ollama
ollama pull gemma3:1b
```

Tarpor `.env` e `OLLAMA_MODEL=gemma3:1b`.

## Desktop app

| Button | Ki hoy |
| --- | --- |
| "Hey Mira" | Chhoto tone baje, window khule, shathe shathe shune |
| Boro mic | Kotha bolo. Chup korle nije thame, abar chaple sathe sathe shesh |
| Mira bolar shomoy mic | Thamiye tomar kotha shune |
| একটানা কথা | Uttor er por nije abar shune, call er moto |
| থামাও / Esc | Sob thamao |
| বাংলা / English / Auto | Tumi kon vashay kotha bolbe |
| Chobi / Ctrl+V / drag | Chobi theke prosno ba math |
| Screen | 3 second por screen dekhe uttor |
| Tala | Private mode |
| Speaker | Voice on/off |
| `⋮` | Notun kore shuru, Mira bondho |
| Ctrl+Space | Mic |

Shutdown, restart ar website kholar age window e **হ্যাঁ, করো** button chapte hoy.
Voice diye eta approve kora jay na.

## Ki bola jay

| Bolo | Ki hoy |
| --- | --- |
| "WhatsApp খোলো", "Spotify চালু করো" | PC te install kora je kono app khule |
| "এখন থেকে 'কোড' বললে VS Code খুলবে" | Nijer nickname save kore |
| "আমার পিসিতে কী কী অ্যাপ আছে?" | App list |
| "x² − 5x + 6 = 0 সমাধান করো" | Dhape dhape solve, sympy diye jachai |
| "sin x / x এর লিমিট x→0", "x² এর ০ থেকে ৩ ইন্টিগ্রাল" | Calculus |
| "৩০ মিনিট পর পানি খেতে মনে করিয়ে দাও" | Reminder |
| "এটা নোট করো: ..." | Note |
| "volume কমাও", "PC lock করো", "screenshot নাও" | PC control |
| "assignment নামের ফাইল খোঁজো" | File khoja |
| "আজ মনটা ভালো নেই" | Mon diye shune kotha bole |

Command Prompt, PowerShell, Registry, uninstall er moto app Mira khole na, nirapottar jonno.

## Settings (`.env`)

| Setting | Ki kore |
| --- | --- |
| `AGENT_NAME`, `USER_NAME` | Mira r nam, tomake ki bole dakbe |
| `STT=gemini` | Mic er kotha Gemini lekhe (Bangla e bhalo). `groq` dile Whisper age |
| `WAKE_WORD=on` | "Hey Mira". `off` dile bondho |
| `WEB_PORT=8765` | App er port, onno program er sathe milte gele bodlao |
| `OLLAMA_MODEL` | Private mode ar offline backup er model |

Windows chalu hole Mira chalu howa bondho korte:
`.venv\Scripts\python main.py --no-startup`
Abar chalu korte: `.venv\Scripts\python main.py --install`

## Mic e kotha vul lekha hole

1. Upore **বাংলা** select kora ache kina dekho.
2. `data\last_voice.wav` shuno (sorboshesh recording, shudhu ei PC te thake).
3. Awaj aste ba bhanga hole: Windows **Settings > System > Sound > Input** e volume 80-100 koro,
   mic er kache theke bolo.
4. Awaj porishkar kintu lekha vul hole `.env` e `STT=groq` diye dekho kon ta bhalo.

## Privacy

- Normal mode e lekha, mone rakha kotha, mic er audio, chobi cloud service e jay
  (Gemini, Groq, ar voice er jonno Microsoft). Gemini free tier er data Google tader
  product unnoti te use korte pare.
- Private mode e shudhu local Ollama cholbe: likhe chat, tool, mic ar voice bondho.
- "Hey Mira" shona pura offline (Vosk). Wake word er age kono audio PC theke baire jay na.
  "Hey Mira" er porer kotha cloud e jay, jemon mic button e.
- App shudhu ei PC theke khola jay (`127.0.0.1`), onno website ba network theke na.
- `.env` (API key) ar `data/` folder (memory, note, app nickname, recording) git e jay na.
  API key kokhono `.env.example` e likho na ba upload koro na.

## Terminal (`start.bat`)

Purono terminal chat o ache:

| Command | Ki hoy |
| --- | --- |
| Khali Enter | Mic on, kotha shesh hole abar Enter |
| `/bn`, `/en`, `/auto` | Mic er vasha |
| `/image C:\path\math.jpg \| eta solve koro` | Chobi theke uttor |
| `/screen eta ki error?` | Screen dekhe uttor |
| `/private`, `/mute`, `/exit` | Private mode, voice, bondho |

## Code

| File | Kaj |
| --- | --- |
| `main.py` | Chalu korar file (`--app`, `--background`, `--install`, `--check`) |
| `agent/web.py` | Desktop app er server (shudhu 127.0.0.1) |
| `agent/static/index.html` | App er screen |
| `agent/wake.py` | "Hey Mira" offline wake word |
| `agent/shortcut.py` | Desktop icon ar Windows start |
| `agent/brain.py` | AI model, instruction, tool chalano |
| `agent/tools.py` | PC control ar math tool er list |
| `agent/apps.py` | PC er app list ar nickname |
| `agent/mathsolve.py` | sympy diye ashol math (alada process e, 20 second limit) |
| `agent/voice.py` | Female voice, mic, Bangla speech-to-text |
| `agent/vision.py` | Chobi ar screen |
| `agent/memory.py` | Memory ar note |
| `agent/calculator.py` | Safe calculator |
| `agent/check.py` | Setup test |
| `agent/cli.py` | Terminal chat |
| `agent/config.py` | `.env` settings |

Notun feature: `agent/tools.py` e function likhe `TOOL_LIST` e ek line add koro.
Desktop app e nije theke cholbe.

Test chalate: `.venv\Scripts\python -m unittest`

## Roadmap

- [x] Phase 1: chat, voice, PC control, chobi, note, reminder, private mode
- [x] Phase 2: PC er je kono app khola, app nickname, `sympy` diye math jachai
- [x] Phase 3a: desktop app, "Hey Mira" wake word, Windows start e chalu, Bangla speech-to-text
- [ ] Phase 3b: tray icon, offline voice input
- [ ] Phase 4: PDF study helper, daily briefing, clipboard translate, file organizer
