# Mira: Bangla + English AI assistant (Windows 11)

Desktop app hishebe chole. **"Hey Mira"** bolle nije khule shune, female voice e Bangla ar
English e uttor dey, PC er app khole, math solve kore ar jachai kore, PDF pore porashonay
sahajjo kore, flashcard e quiz ney, Downloads gochay, weather ar khobor bole, Gmail ar
Calendar pore, mood diary rakhe. Sob free tier diye chole.

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

Tarpor Desktop er Mira icon e chap dao. Windows er shathe chalu howa purono Mira cholte thakle notun
Mira nije oita bondho kore notun ta chalu kore. `⋮` > **মিরার ভয়েস পরীক্ষা** e ekhon kon version cholche
ta lekha thake.

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
| Majher rongin gol (orb) | Chap dao, kotha bolo. Chup korle nije thame, abar chaple sathe sathe shesh |
| Mira bolar shomoy orb e chap | Thamiye tomar kotha shune |
| একটানা কথা | Uttor er por nije abar shune, call er moto |
| থামাও / Esc | Sob thamao |
| বাংলা / English / Auto | Tumi kon vashay kotha bolbe |
| Chobi / Ctrl+V / drag | Chobi ba PDF/text file theke prosno, math, porashona |
| Screen | 3 second por screen dekhe uttor |
| Tala | Private mode |
| Speaker | Voice on/off |
| `⋮` | Aajker briefing, flashcard quiz, notun kore shuru, Mira bondho |
| Clock er pashe **M** icon | Kholo, kotha bolo, private, voice bondho, Mira bondho |
| Ctrl+Space | Mic |

Orb dekhe bojha jay Mira ki korche: chup thakle dhire nishshash er moto nore, shunar shomoy
tomar awaj er sathe dheu chhoray, bhabar shomoy kinara diye rekha ghore, bolar shomoy dhukpuk kore.
Private mode e nil-sobuj hoy. Windows e "animation bondho" setting on thakle orb thir thake.

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
| "এই PDF টা সহজ করে বোঝাও", "Downloads এ physics নামের PDF এর ৩ নম্বর পাতা" | PDF study helper |
| "এই চ্যাপ্টার থেকে ১০টা ফ্ল্যাশকার্ড বানাও", "আজকের ফ্ল্যাশকার্ড দিয়ে কুইজ নাও" | Flashcard, je gulo vul hoy segulo abar ashe |
| "আজকের ব্রিফিং দাও" | Tarikh, weather, calendar, unread mail, flashcard, note, khobor |
| "কপি করা লেখাটা বাংলায় অনুবাদ করো", "অনুবাদটা কপি করে দাও" | Clipboard translate |
| "Downloads গুছিয়ে দাও", "আগের মতো করে দাও" | File type onujayi folder e shajano (age jiggesh kore, undo kora jay) |
| "আজকের আবহাওয়া কেমন?", "আজকের খেলার খবর", "সালোকসংশ্লেষণ কী?" | Weather, khobor, Wikipedia |
| "আমার unread mail গুলো বলো", "কাল আমার কী কী আছে?" | Gmail ar Calendar (shudhu pora) |
| "আজকের মুড ৩ লিখে রাখো", "এই সপ্তাহে আমার মুড কেমন ছিল?" | Mood diary, shudhu ei PC te |
| "Anika কে WhatsApp এ লেখো আমি ১০ মিনিটে আসছি" | WhatsApp message (age onumoti chay) |
| "Rafi র নম্বর 01712345678 সেভ করো" | WhatsApp contact save |
| "ctrl s চাপো", "এটা টাইপ করো: ...", "উইন্ডো মিনিমাইজ করো", "নতুন ট্যাব খোলো" | Keyboard, typing, window, tab |
| "গান থামাও", "পরের গান", "ব্রাইটনেস ৬০ করো", "Downloads ফোল্ডার খোলো" | Media, brightness, folder |
| "Chrome বন্ধ করো", "ব্যাটারি কত?", "পিসি স্লিপে দাও" | App bondho (onumoti niye), battery/RAM/disk, sleep |
| "স্ক্রিনে কী আছে?", "Search বক্সে ক্লিক করো", "প্রথম ভিডিওটা চালাও" | Screen dekhe bola, describe kore click |
| "YouTube এ আরিজিতের গান চালাও" | Onek dhaper kaj: khola, dekha, click, type, abar dekha |
| "কোন কোন উইন্ডো খোলা?", "Chrome এ যাও" | Open window list ar shekhane jawa |
| "Downloads এ cv.pdf টা Documents\\Job এ সরাও", "নতুন ফোল্ডার বানাও", "এটা মুছে দাও" | File/folder banano, nam bodlano, sorano, copy, Recycle Bin e fela (onumoti niye) |
| "Downloads এর cv.pdf খোলো", "Downloads এ কী আছে?" | File khola ar folder dekha |
| "Wi-Fi সেটিংস খোলো", "Night light", "Bluetooth" | Windows Settings er page |

Tumi Mira r window e kotha bolleo key chapa ar type kora jay tumi shesh je app e chile shekhane.

Click ar file er nirapotta: delete, send, pay, buy, install er moto kichute click er age Mira onumoti chay.
File er kaj shudhu Desktop, Documents, Downloads, Pictures, Music, Videos er moddhe, ar muche fele na,
Recycle Bin e pathay. Program ba script (.exe, .bat, .ps1...) Mira khole na.

Command Prompt, PowerShell, Registry, uninstall er moto app Mira khole na. Command window samne thakle
Mira tate type ba key chape na, ar Win+R ba Win+X chape na, jate keu bhul kore kono command chalate na pare.

## WhatsApp

1. Prothome nombor save koro: "Anika র নম্বর 01712345678 সেভ করো". Nombor shudhu `data\contacts.json` e thake.
2. Tarpor bolo: "Anika কে WhatsApp এ লেখো আমি আসছি".
3. Mira ke ke message pabe ar ki likha thakbe dekhabe. **হ্যাঁ, করো** chaple WhatsApp khule message likhe Enter chape.

WhatsApp Desktop app install thakle Mira sheta use kore (taratari ar nirbhorjoggo). Na thakle web.whatsapp.com
e notun tab khule. Onno tab e WhatsApp Web khola thakle WhatsApp "Use here" chaite pare, tokhon oita chap dao.
Nije Enter chapte chaile `.env` e `WHATSAPP_AUTOSEND=off`.

## Settings (`.env`)

| Setting | Ki kore |
| --- | --- |
| `AGENT_NAME`, `USER_NAME` | Mira r nam, tomake ki bole dakbe |
| `VISION_MODEL` | Screen dekhe click er model (default `GEMINI_MODEL`). Click bhul jaygay porle aro boro Gemini model dao |
| `VOICE_MODE=direct` | Gemini tomar voice shune ager kotha mile ekbar e bujhe uttor dey (taratari). `separate` dile age lekha, tarpor uttor |
| `SILENCE_SECONDS=0.9` | Koto second chup thakle kotha shesh dhorbe. Kotha majhe kete gele 1.2 koro, aro fast chaile 0.7 |
| `STT=gemini` | `separate` mode e kotha Gemini lekhe. `groq` dile Whisper age |
| `WAKE_WORD=on` | "Hey Mira". `off` dile bondho |
| `WEB_PORT=8765` | App er port, onno program er sathe milte gele bodlao |
| `TRAY=on` | Clock er pashe icon. `off` dile nai |
| `CITY=Dhaka` | Weather er shohor |
| `GEMINI_THINKING=low` | Gemini koto bhabbe. `low` taratari, `medium`/`high` kothin prosne bhalo |
| `WHATSAPP=auto`, `WHATSAPP_AUTOSEND=on` | WhatsApp Desktop na web, ar nije Enter chapbe kina |
| `OLLAMA_MODEL` | Private mode ar offline backup er model |

Windows chalu hole Mira chalu howa bondho korte:
`.venv\Scripts\python main.py --no-startup`
Abar chalu korte: `.venv\Scripts\python main.py --install`

## Internet na thakle

Net na thakle mic shudhu **English** bojhe (upore English select koro), offline Vosk model diye.
Bangla kotha bujhte net lagbe. Private mode e o English mic chole, kono audio PC theke baire jay na.

## Gmail ar Calendar (optional, ekbar setup)

Mira shudhu mail ar calendar **pore**, kokhono pathay, muche, ba bodlay na.

1. [Google Cloud Console](https://console.cloud.google.com/) e notun project banao.
2. **APIs & Services > Library** theke **Gmail API** ar **Google Calendar API** Enable koro.
3. **OAuth consent screen**: External, app er nam "Mira", nijer email dao. **Test users** e nijer
   Gmail add koro.
4. **Credentials > Create credentials > OAuth client ID > Desktop app**. Download JSON.
5. File ta `data\google_credentials.json` nam e project folder er `data` folder e rakho.
6. Mira ke bolo "আমার unread mail গুলো বলো". Prothom bar browser e Google sign in chaibe,
   "Google hasn't verified this app" ashle **Continue** dao (eta tomar nijer app).

Token `data\google_token.json` e thake. Bondho korte file ta muche dao, ar
[Google account permissions](https://myaccount.google.com/permissions) theke Mira ke remove koro.

## Mira voice e kotha na bolle

Mira r voice ekhon Mira r window nijei bajay (Edge/Chrome er sound), tai Windows e browser e sound
bajle Mira o bajbe. Window lukano thakle ba browser na dile Python bajay.

1. `⋮` > **মিরার ভয়েস পরীক্ষা** chapo. Chat e dhap dhore lekha ashbe: voice toiri holo kina, window theke
   baje kina, na baje Python theke baje kina. Kothay "হয়নি" lekha, sheta dekhe bojha jay somossa kothay.
2. "জানালায় একবার ক্লিক করো" lekha ashle window e jekono jaygay ekbar click koro.
3. Upore speaker button e kata dag thakle voice bondho, chap dao.
4. Private mode e Mira voice e bole na (tala button).
5. Windows er volume ar kon speaker/headphone select kora ache dekho.
6. Bangla voice er jonno internet lage. Na pele English uttor Windows er nijer voice e bole.

"Hey Mira" nije nije chalu hole `⋮` > **"Hey Mira" বন্ধ করো**. "Hey Mira" shune chalu hole chat e
**"Hey Mira" শুনে নিজে চালু** lekha thake.

## Speed

Uttor er niche "x সেকেন্ডে" dekhay. Mira chalu holei voice ar model er connection gorom kore rakhe,
Gemini ke kom bhabte bole (`GEMINI_THINKING=low`), ar prothom bakko toiri holei bola shuru kore.
Aro taratari chaile `.env` e `SILENCE_SECONDS=0.7`.

## Mic e kotha vul lekha hole

1. Upore **বাংলা** select kora ache kina dekho.
2. `data\last_voice.wav` shuno (sorboshesh recording, shudhu ei PC te thake).
3. Awaj aste ba bhanga hole: Windows **Settings > System > Sound > Input** e volume 80-100 koro,
   mic er kache theke bolo.
4. Awaj porishkar kintu lekha vul hole `.env` e `VOICE_MODE=separate` ba `STT=groq` diye dekho kon ta bhalo.

Mira r protiti uttor er niche **"x সেকেন্ডে"** lekha thake: tumi chup korar por uttor toiri hote koto shomoy legeche.
Uttor shuru hoy prothom bakko toiri holei, baki gulo bolar shomoy pichone toiri hoy.

## Privacy

- Normal mode e lekha, mone rakha kotha, mic er audio, chobi cloud service e jay
  (Gemini, Groq, ar voice er jonno Microsoft). Gemini free tier er data Google tader
  product unnoti te use korte pare.
- Private mode e shudhu local Ollama cholbe: tool, file, Bangla mic ar voice bondho, English mic offline.
- PDF, clipboard, mail, calendar er lekha shudhu tumi chaile Gemini te jay, uttor toirir jonno.
- Mood diary, flashcard, note, app nickname shudhu `data/` folder e thake, kothao upload hoy na.
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
| `agent/tray.py` | Clock er pashe icon |
| `agent/files.py` | PDF/text pora, clipboard, folder gochano ar undo |
| `agent/info.py` | Weather (Open-Meteo), khobor (Google News), Wikipedia |
| `agent/google.py` | Gmail ar Calendar, shudhu pora |
| `agent/study.py` | Flashcard ar mood diary |
| `agent/daily.py` | Aajker briefing |
| `agent/control.py` | Keyboard, typing, window, media, app bondho, brightness, file, Settings, WhatsApp |
| `agent/screen.py` | Screen dekha, describe kore click, window list ar switch, ager app e focus |
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
- [x] Phase 3b: tray icon, net chara English voice input
- [x] Phase 4: PDF study helper, daily briefing, clipboard translate, file organizer
- [x] Phase 5: Gmail/Calendar (read only), weather/khobor/Wikipedia, flashcard study mode, mood diary
