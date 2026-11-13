ROTOGO BERYLLIUM v7.1 — OVERVIEW
=================================
(formerly "Local Assistant")

An offline Windows assistant in a single Python file (no dependencies to
install). It opens apps and sites, searches Google, shows weather and
currency rates right in the chat, calculates expressions, sets timers,
translates, creates folders, .txt/.docx documents, real .pptx
presentations and .xlsx spreadsheets, takes notes and finds files.

NEW IN v7.1 — TWO LANGUAGES IN ONE APP
  - A Russian / English interface toggle right in the window:
    the "RU"/"EN" button in the top-right corner of the header, OR the
    command "язык" / "english" / "russian" / "language".
  - The choice is saved to lang.txt and applied on the next launch.
    Default is Russian.
  - Commands are understood in both languages: type "weather" or
    "погода", "open notepad" or "открой блокнот".
  - In English mode, Wikipedia comes from en.wikipedia.org and Gemini
    prompts / slide and document text are generated in English.

MINI-APPS RIGHT IN THE CHAT
  1. WEATHER: "weather" / "weather in moscow" — temperature, feels like,
     wind, humidity, day min-max (wttr.in + Open-Meteo, no keys).
  2. RATES: "rates" / "rates usd" — fresh Central Bank of Russia rates
     with daily change (▲/▼). Cached for 10 minutes.
  3. CALCULATOR: "calculate 2+2*10", "how much is 15% of 200", "2^10",
     parentheses, remainder %. Safe: no eval.
  4. TIMER: "timer for 5 minutes", "remind me in 30 seconds" — window,
     chat bubble and sound.
  5. TRANSLATE: "translate hello world" — Gemini (if a key is set) or
     Google Translate in the browser.
  6. EXCEL SPREADSHEETS: "make a spreadsheet about X" — a real .xlsx:
     filled header row (frozen), autofilter, column widths, thousands
     separators.
  7. FILE SEARCH: "find file report" — searches the desktop, Documents
     and Downloads; newest first.
  8. COIN AND DICE: "coin", "dice", "random number 1 to 100".

INTERFACE
  - Windows 11-style dark title bar + custom "RB" icon;
  - two rows of quick command chips (8 total, language-aware);
  - bubbles ease in; progress in a single bubble;
  - right-click a message to copy its text;
  - Up/Down arrows for command history; clock in the header.

PROJECT FILES
  rotogo.pyw     — the program (single file, no libraries)
  start.bat      — launch without a console (double-click)
  gemini_key.txt — Gemini API key (NOT INCLUDED; created by you, see
                   below; optional)
  lang.txt       — chosen interface language (created by the program)
  README_EN.txt  — this file
  README_RU.txt  — overview in Russian

HOW TO RUN
----------
Requires Python 3.8+ (python.org). No libraries to install.

    Option 1 (recommended): double-click start.bat
    Option 2: double-click rotogo.pyw (runs via pythonw)
    Option 3: from a command line,  python rotogo.pyw

THE GEMINI KEY IS OPTIONAL
--------------------------
The app works fully WITHOUT a key: text for presentations, documents and
spreadsheets comes from Wikipedia and the built-in knowledge base;
weather and rates come from open sources. A key is only needed if you
want Google Gemini (flash series) to write the text and to help the
assistant understand very non-standard phrasings.

    How to connect it (free):
      1. aistudio.google.com → "Get API key" (starts with AIza or AQ.).
      2. Inside the app type "connect google" and paste the key, OR
         "key from file" and pick a txt file with the key.
      3. The key is saved to gemini_key.txt next to the program and
         NEVER leaves your computer.

    IMPORTANT for GitHub: do NOT commit gemini_key.txt — it is in
    .gitignore. This build ships WITHOUT a key.

MAIN COMMANDS (type "help" inside the app)
  weather [in city]                         weather in chat
  rates [usd|eur|cny]                       Central Bank rates
  calculate 2+2*10 / how much is 15% of 200 calculator
  timer for 5 minutes                       remind with sound and window
  translate <text>                          Gemini or Google Translate
  coin / dice                               randomness
  google <query>                            Google search
  open <app/site>                           notepad, roblox, steam, youtube…
  create folder <name>                      [on desktop / in documents]
  create text document about X              .txt with real text
  create document (word) about X            .docx for Word
  make a presentation about X               .pptx with photos and facts;
                                            you can add "in folder <name>"
                                            and "10 slides"
  make a spreadsheet about X                .xlsx (Excel) with styling
  take a note <text>                        .txt file on the desktop
  find file <name>                          search desktop/docs/downloads
  connect google                            paste a Gemini API key
  key from file                             pick a txt file with the key
  remove key                                forget the key
  time / date / specs                       time, date, PC specs
  english / russian / language              switch the interface language
  clear chat                                clear history
  bye                                       quit

Type however you like — abbreviations, conversational variants and typos
are supported. Up/Down arrows — command history. Right-click a message —
copy.

WHERE THE TEXT COMES FROM (in order, whichever works first):
  a) Google Gemini (flash series) — if a key is connected;
  b) Wikipedia — real facts and photos, no keys needed;
  c) the built-in knowledge base — works without internet.
The source is shown honestly in the reply and on the final slide. Photos
come from Wikipedia, Wikimedia Commons, Openverse, Flickr (no keys);
there is no image generation via an API — only real photos.

IF SOMETHING DOES NOT WORK
  - The app did not open — open error_log.txt next to it.
  - The work log is rotogo.log (open it in a text editor).
  - "Google rejected the request from this network" — the Gemini API
    does not work over this network/VPN. Change the network; Wikipedia,
    weather, rates and the offline base keep working.
  - "Gemini request limit exhausted" — the free key ran out of quota:
    wait a minute and try again.
  - "Python not found" when running start.bat — install Python from
    python.org and check "Add python.exe to PATH".
