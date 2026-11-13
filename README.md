# RotoGo Beryllium

**Offline desktop assistant for Windows — one Python file, zero dependencies.**

RotoGo Beryllium — офлайн-помощник для Windows на одном файле Python (без
библиотек). Открывает программы и сайты, ищет в Google, показывает погоду и
курсы валют в чате, считает, ставит таймеры, переводит, создаёт папки,
документы `.txt`/`.docx`, настоящие презентации `.pptx` и таблицы `.xlsx`,
ведёт заметки и ищет файлы. Интерфейс переключается между **русским** и
**английским** одним кликом.

[Русское описание](README_RU.txt) · [English overview](README_EN.txt)

---

## ✨ What it does

- **Mini-apps in the chat:** weather (`wttr.in` + Open-Meteo), Central Bank of
  Russia currency rates, a safe calculator (no `eval`), timers, translation,
  coin/dice.
- **Files & documents:** create folders, `.txt`, `.docx` (Word), real `.pptx`
  presentations with photos and facts, and `.xlsx` spreadsheets with a styled
  header, autofilter and frozen row.
- **Open apps & sites:** launch Notepad, Roblox, Steam, YouTube… installed
  programs are found via Start-menu shortcuts; unknown names are fuzzy-matched.
- **Search the web** with Google, **find files** on the desktop / Documents /
  Downloads, **take notes**.
- **Understands typos** and varied phrasings; right-click a message to copy it;
  Up/Down arrows scroll your command history.

## 🌐 Two languages, one app (v7.1)

Switch the interface between **Russian** and **English** at any time:

- the **RU / EN** button in the top-right corner of the header, or
- the command `язык` / `english` / `russian` / `language`.

Commands are bilingual — type `погода` or `weather`, `открой блокнот` or
`open notepad`. The choice is saved to `lang.txt` and remembered on the next
launch (default: Russian). In English mode, Wikipedia is fetched from
`en.wikipedia.org` and Gemini prompts / generated text are in English.

## 🚀 Install & run

Requires **Python 3.8+** from [python.org](https://python.org). No libraries to
install — everything is in the single `rotogo.pyw`.

```bash
git clone https://github.com/<your-user>/rotogo-beryllium.git
cd rotogo-beryllium
```

Then on Windows:

| Way | How |
| --- | --- |
| Recommended | double-click **`start.bat`** (no console window) |
| Via pythonw | double-click **`rotogo.pyw`** |
| From terminal | `python rotogo.pyw` (auto-detaches from the console) |

> If `start.bat` says *"Python not found"* — reinstall Python and tick
> **"Add python.exe to PATH"**.

## 🔑 The Gemini key is optional

The app works **fully without a key**: text for presentations, documents and
spreadsheets comes from Wikipedia and the built-in knowledge base; weather and
rates come from open sources. Add a key only if you want Google Gemini
(flash series) to write the text and to help with unusual phrasings.

1. Get a free key at [aistudio.google.com](https://aistudio.google.com) →
   **"Get API key"** (starts with `AIza` or `AQ.`).
2. In the app type `connect google` and paste the key — or `key from file`
   and pick a `.txt` file containing it.
3. The key is stored in **`gemini_key.txt`** next to the program and **never
   leaves your computer**.

> ⚠️ **Never commit `gemini_key.txt`.** It is listed in `.gitignore`. This
> repository ships **without** a key.

## 📋 Main commands

Type `help` / `помощь` inside the app for the full list.

| Command (RU / EN) | What it does |
| --- | --- |
| `погода [в городе]` / `weather [in city]` | weather in chat |
| `курс [доллара]` / `rates [usd]` | Central Bank rates |
| `посчитай 2+2*10` / `calculate 2+2*10` | calculator (`+ - * / ^ %`, parentheses) |
| `таймер на 5 минут` / `timer for 5 minutes` | remind with sound + window |
| `переведи <text>` / `translate <text>` | Gemini or Google Translate |
| `монетка` / `coin`, `кубик` / `dice` | randomness |
| `загугли <q>` / `google <q>` | Google search |
| `открой <app/site>` / `open <app/site>` | launch apps/sites |
| `создай папку <name>` / `create folder <name>` | new folder |
| `создай текстовый документ про X` / `create a text document about X` | `.txt` |
| `создай документ (ворд) про X` / `create word about X` | `.docx` |
| `создай презентацию про X` / `make a presentation about X` | `.pptx` with photos |
| `создай таблицу про X` / `make a spreadsheet about X` | `.xlsx` (Excel) |
| `запиши заметку <text>` / `take a note <text>` | `.txt` on the desktop |
| `найди файл <name>` / `find file <name>` | search desktop/docs/downloads |
| `подключи гугл` / `connect google` | paste a Gemini key |
| `язык` / `english` / `russian` / `language` | switch interface language |
| `время` / `time`, `дата` / `date`, `характеристики` / `specs` | info |
| `очисти чат` / `clear chat`, `пока` / `bye` | clear / quit |

## 🧠 Where the text comes from

In order, whichever succeeds first:

1. **Google Gemini** (flash series) — if a key is connected;
2. **Wikipedia** — real facts and photos, no keys needed;
3. **the built-in knowledge base** — works without internet.

The source is shown honestly in the reply and on the final slide. Photos come
from Wikipedia (RU + EN), Wikimedia Commons, Openverse and Flickr — all
key-less. There is **no image generation via an API**: only real photos, and a
single photo never appears on two slides.

## 🩹 Troubleshooting

- The app did not open → read **`error_log.txt`** next to it.
- Work log → **`rotogo.log`** (open in a text editor).
- *"Google rejected the request from this network"* → the Gemini API is blocked
  on this network/VPN; switch networks — Wikipedia, weather, rates and the
  offline base keep working.
- *"Gemini request limit exhausted"* → the free key ran out of quota; wait a
  minute and retry.

## 📁 Project layout

```
rotogo.pyw        # the program (single file, no dependencies)
start.bat         # launch without a console
gemini_key.txt    # your Gemini key (NOT shipped; gitignored; optional)
lang.txt          # chosen interface language (created at runtime)
README_RU.txt     # Russian overview
README_EN.txt     # English overview
error_log.txt     # written if startup fails
rotogo.log        # runtime log
```

## License

Personal-use desktop tool. Provided as-is. The bundled knowledge base, weather
(`wttr.in`, Open-Meteo), rates (Central Bank of Russia / cbr-xml-daily.ru),
Wikipedia, Wikimedia Commons, Openverse and Flickr sources all work without API
keys.
