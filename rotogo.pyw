#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RotoGo Beryllium v7.0 — FINAL
=============================
Локальный ассистент для Windows (ранее — «Локальный Ассистент» 5.x).
Только стандартный Python, без библиотек: скачал — и работает.

ГЛАВНОЕ В ФИНАЛЬНОЙ ВЕРСИИ 7.0 «BERYLLIUM FINAL»:

МИНИ-ПРИЛОЖЕНИЯ ПРЯМО В ЧАТЕ (новое):
  1. ПОГОДА: «погода» / «погода в москве» — температура, ощущается,
     ветер и влажность прямо в чате (wttr.in, без ключа); при сбое
     сети открывается сайт.
  2. КУРС ВАЛЮТ: «курс» / «курс доллара» — свежие курсы ЦБ РФ
     (доллар, евро, юань...) с изменением за день.
  3. КАЛЬКУЛЯТОР: «посчитай 2+2*10» / «сколько будет 15% от 200» —
     безопасный вычислитель (+ - * / ^ %, скобки, проценты).
  4. ТАЙМЕР: «таймер на 5 минут» / «напомни через 10 минут» —
     по истечении окно, пузырь в чате и звуковой сигнал.
  5. ПЕРЕВОД: «переведи ...» — Gemini (если подключён ключ) или
     страница Google Переводчика.
  6. ТАБЛИЦЫ EXCEL: «создай таблицу про X» — настоящий .xlsx с
     оформлением (заголовки, заливка, закреплённая шапка).
  7. ПОИСК ФАЙЛОВ: «найди файл отчет» / «открой файл отчет» — поиск
     по рабочему столу, документам и загрузкам (нечёткий).
  8. МОНЕТКА И КУБИК: «монетка» / «кубик».

ИНТЕРФЕЙС:
  - тёмный титул окна в стиле Windows 11 + собственный значок;
  - новые двухрядные быстрые команды (8 чипов);
  - плавное появление пузырей, живой прогресс в одном пузыре;
  - копирование любого сообщения правой кнопкой мыши;
  - история ввода стрелками вверх/вниз (как в терминале);
  - часы в шапке; шапка перерисовывается только при изменениях
    (раньше — каждую секунду) — интерфейс стал заметно легче.

СКОРОСТЬ:
  - кэш точных названий статей Википедии и кэш содержания по теме:
    повторная презентация по той же теме собирается мгновенно;
  - кэш погоды и курсов на 10 минут;
  - опрос очередей ускорен (70 мс) — чат реагирует мгновенно.

Из 6.0 «BERYLLIUM» (кратко): параллельный поиск фото по 5 источникам,
один вызов Gemini вместо двух, фото стартует не ждая текста, кэш
рабочей модели, живой прогресс, до 10 разделов в презентации.

Запуск:  pythonw rotogo.pyw   (или двойной клик по start.bat)
"""

import os
import re
import sys
import ast
import json
import math
import time
import queue
import random
import shutil
import struct
import base64
import zipfile
import platform
import datetime
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
import subprocess
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from xml.sax.saxutils import escape

APP_TITLE = 'RotoGo Beryllium'
APP_VERSION = '7.1'

# ----------------------------------------------------------------------------
# Логирование (рядом с программой, чтобы можно было прислать при проблемах)
# ----------------------------------------------------------------------------

def _script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()

LOG_PATH = os.path.join(_script_dir(), 'rotogo.log')


def log(msg):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Отсоединение от консоли — главное исправление «закрывается вместе с cmd»
# ----------------------------------------------------------------------------

def detach_from_console():
    """Отключает процесс от консоли Windows.

    После этого закрытие окна cmd (из которого запустили программу)
    больше не завершает приложение: графическое окно продолжает работать.
    Стандартные потоки вывода перенаправляются в никуда, чтобы ничто
    не пыталось писать в уже закрытую консоль.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow():
            kernel32.FreeConsole()
            try:
                devnull_w = open(os.devnull, 'w')
                sys.stdout = devnull_w
                sys.stderr = devnull_w
                sys.stdin = open(os.devnull, 'r')
            except Exception:
                pass
            log('Отсоединился от консоли: закрытие cmd больше не закроет приложение')
    except Exception as e:
        log('Не удалось отсоединиться от консоли: %r' % e)


# ----------------------------------------------------------------------------
# Текстовые утилиты и нечёткое сравнение (устойчивость к опечаткам)
# ----------------------------------------------------------------------------

# латинские буквы-двойники внутри русских слов (частая причина «непонимания»)
_LOOKALIKE = {'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'y': 'у',
              'x': 'х', 'k': 'к', 'm': 'м', 't': 'т', 'b': 'в', 'h': 'н'}


def normalize(text):
    """Приводит текст к каноническому виду: нижний регистр, ё->е,
    без пунктуации, латинские двойники заменены на кириллицу."""
    t = text.lower().replace('ё', 'е')
    t = re.sub(r'[^\w\s]', ' ', t, flags=re.UNICODE)
    t = t.replace('_', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    out = []
    for w in t.split():
        if re.search(r'[а-я]', w):
            w = ''.join(_LOOKALIKE.get(ch, ch) for ch in w)
        out.append(w)
    return ' '.join(out)


def levenshtein(a, b):
    """Расстояние Левенштейна (классический алгоритм, короткие слова)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def sim(a, b):
    """Похожесть двух слов от 0 до 1 (1 — совпадение)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    m = max(len(a), len(b))
    return 1.0 - levenshtein(a, b) / m


def word_thr(a, b):
    """Порог похожести в зависимости от длины слова.

    Короткие слова (до 3 букв) должны совпадать точно — иначе будет
    мусор; длинные слова допускают 1-2 опечатки."""
    m = max(len(a), len(b))
    if m <= 3:
        return 1.0
    if m <= 6:
        return 0.75
    return 0.70


def best_fuzzy(word, targets):
    """Лучшее совпадение слова с одним из образцов (0 — нет совпадения)."""
    best = 0.0
    for t in targets:
        s = sim(word, t)
        if s >= word_thr(word, t) and s > best:
            best = s
    return best


# ----------------------------------------------------------------------------
# База знаний: приложения, сайты, ответы
# ----------------------------------------------------------------------------

# kind: 'exe'  — запуск через os.startfile (программа Windows)
#        'site' — открыть в браузере
APPS = {
    'блокнот': ('exe', 'notepad'),
    'калькулятор': ('exe', 'calc'),
    'paint': ('exe', 'mspaint'),
    'паинт': ('exe', 'mspaint'),
    'графический редактор': ('exe', 'mspaint'),
    'проводник': ('exe', 'explorer'),
    'панель управления': ('exe', 'control'),
    'диспетчер задач': ('exe', 'taskmgr'),
    'командная строка': ('exe', 'cmd'),
    'терминал': ('exe', 'cmd'),
    'консоль': ('exe', 'cmd'),
    'cmd': ('exe', 'cmd'),
    'смд': ('exe', 'cmd'),
    'кмд': ('exe', 'cmd'),
    'настройки': ('exe', 'ms-settings:'),
    'параметры': ('exe', 'ms-settings:'),
    'корзина': ('exe', '::{645FF040-5081-101B-9F08-00AA002F954E}'),
    'браузер': ('site', 'https://www.google.com'),
    'google': ('site', 'https://www.google.com'),
    'гугл': ('site', 'https://www.google.com'),
    'гугл хром': ('site', 'https://www.google.com'),
}

SITES = {
    'погода': 'https://wttr.in/?lang=ru',
    'ютуб': 'https://www.youtube.com',
    'youtube': 'https://www.youtube.com',
    'музыка': 'https://music.youtube.com',
    'музыку': 'https://music.youtube.com',
    'музыке': 'https://music.youtube.com',
    'википедия': 'https://ru.wikipedia.org',
    'почта': 'https://mail.google.com',
    'gmail': 'https://mail.google.com',
    'переводчик': 'https://translate.google.com',
    'карты': 'https://www.google.com/maps',
    'телеграм': 'https://web.telegram.org',
    'вк': 'https://vk.com',
    'вконтакте': 'https://vk.com',
    'инстаграм': 'https://www.instagram.com',
    'твиттер': 'https://twitter.com',
    'гитхаб': 'https://github.com',
    'дискорд': 'https://discord.com/app',
    'спотифай': 'https://open.spotify.com',
    'твич': 'https://www.twitch.tv',
    'роблокс': 'https://www.roblox.com',
    'roblox': 'https://www.roblox.com',
    'стим': 'https://store.steampowered.com',
    'steam': 'https://store.steampowered.com',
    'майнкрафт': 'https://www.minecraft.net',
    'minecraft': 'https://www.minecraft.net',
    'фортнайт': 'https://www.fortnite.com',
    'гугл диск': 'https://drive.google.com',
}

# английские имена приложений и сайтов (двуязычный словарь — v7.1)
APPS.update({
    'notepad': ('exe', 'notepad'), 'calculator': ('exe', 'calc'),
    'calc app': ('exe', 'calc'), 'paint app': ('exe', 'mspaint'),
    'file explorer': ('exe', 'explorer'), 'explorer': ('exe', 'explorer'),
    'control panel': ('exe', 'control'), 'task manager': ('exe', 'taskmgr'),
    'command prompt': ('exe', 'cmd'), 'terminal app': ('exe', 'cmd'),
    'settings app': ('exe', 'ms-settings:'), 'recycle bin': (
        'exe', '::{645FF040-5081-101B-9F08-00AA002F954E}'),
})
SITES.update({
    'weather': 'https://wttr.in/?lang=en', 'youtube music': 'https://music.youtube.com',
    'music': 'https://music.youtube.com', 'wikipedia': 'https://en.wikipedia.org',
    'mail': 'https://mail.google.com', 'email': 'https://mail.google.com',
    'translator': 'https://translate.google.com', 'maps': 'https://www.google.com/maps',
    'telegram': 'https://web.telegram.org', 'instagram': 'https://www.instagram.com',
    'twitter': 'https://twitter.com', 'github': 'https://github.com',
    'discord': 'https://discord.com/app', 'spotify': 'https://open.spotify.com',
    'twitch': 'https://www.twitch.tv', 'fortnite': 'https://www.fortnite.com',
    'google drive': 'https://drive.google.com', 'google': 'https://www.google.com',
})

WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг',
            'пятница', 'суббота', 'воскресенье']
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

GREETINGS = [
    'Привет! Чем могу помочь? Если нужны команды — напишите «помощь».',
    'Здравствуй! Я на связи. Что будем делать?',
    'Привет-привет! Слушаю вас.',
    'И вам привет! Готов к работе.',
]

THANKS_REPLIES = ['Всегда пожалуйста!', 'Обращайтесь!', 'Рад помочь.']

JOKES = [
    'Программист ставит на ночь два стакана: полный — если захочет пить, '
    'и пустой — если не захочет.',
    'Оптимист говорит: «стакан наполовину полон». Пессимист: «наполовину пуст». '
    'Программист: «стакан в два раза больше, чем нужно».',
    'Есть два типа людей: те, кто делает резервные копии, '
    'и те, кто ещё не терял данные.',
    '— Дорогой, сходи в магазин, купи батон хлеба. Если будут яйца — возьми десяток. '
    'Программист вернулся с десятью батонами.',
    'Сын спрашивает программиста: — Пап, а почему солнце каждое утро встаёт? '
    '— Хороший вопрос. Наверное, кто-то настроил автозапуск.',
    '— Почему программисты не любят природу? — Слишком много багов.',
    'Компьютер работает идеально ровно до момента, '
    'когда нужно показать результат начальству.',
]

WHO_TEXT = (
    'Я RotoGo Beryllium v%s — офлайн-помощник для вашего компьютера.\n'
    'Умею: открывать программы и сайты (в том числе искать установленные '
    'по ярлыкам меню «Пуск»), искать в Google, показывать погоду и курсы '
    'валют прямо в чате, считать примеры и проценты, ставить таймеры, '
    'переводить, создавать папки, документы .txt/.docx, настоящие '
    'презентации .pptx и таблицы .xlsx, вести заметки, искать файлы, '
    'показывать время, дату и характеристики компьютера.\n'
    'Понимаю опечатки и разные формулировки. Список команд — «помощь».'
) % APP_VERSION

HELP_TEXT = """ЧТО Я УМЕЮ (v7 FINAL)

Мини-приложения прямо в чате:
  погода [в городе]              — температура, ветер, влажность в чате
  курс [доллара|евро|юаня]        — курсы ЦБ РФ с изменением за день
  посчитай 2+2*10 / 15% от 200    — калькулятор (+ - * / ^ % и скобки)
  таймер на 5 минут               — напомню окном, пузырём и звуком
  переведи <текст>                — Gemini или Google Переводчик
  монетка / кубик                 — момент случайности

Поиск и интернет:
  загугли <запрос>               — поиск в Google
  открой <приложение или сайт>   — блокнот, роблокс, стим, ютуб...;
                                    незнакомые программы ищутся
                                    по ярлыкам меню «Пуск»
  открой папку <имя>              — открыть папку в Проводнике

Файлы и документы:
  создай папку <имя>              — можно добавить «на рабочем столе»
  создай текстовый документ про <тема> — .txt с настоящим текстом;
                                    можно «в папку/в папке <имя>»
  создай документ (ворд) про <тема> — .docx для Word, с заголовками
  создай презентацию про <тема>  — настоящий .pptx с фактами и фото;
                                    можно «в папку/в папке <имя>» и «на 10 слайдов»
  создай таблицу про <тема>       — настоящий .xlsx (Excel): шапка,
                                    автофильтр, закреплённая строка
  запиши заметку <текст>          — короткая заметка .txt на рабочем столе
  найди файл <имя>               — поиск на столе, в документах, загрузках
  открой файл <имя>               — найти и сразу открыть

Текст для презентаций, документов и таблиц пишут (по очереди,
что раньше сработает):
  1. Google Gemini (серия flash, рабочая модель запоминается) —
     если подключён ключ; он же помогает понимать
     необычные формулировки команд и переводит;
  2. Википедия — реальные факты и фото по теме, ключи не нужны;
  3. встроенная база знаний — работает даже без интернета.
  Фото ищутся сразу в 5 источниках ПАРАЛЛЕЛЬНО: русская и английская
  Википедия, Wikimedia Commons, Openverse, Flickr.
  подключи гугл  — вставить API-ключ Gemini (aistudio.google.com,
                    кнопка «Get API key»); ключ хранится только у вас
  ключ из файла  — выбрать txt-файл с ключом, копировать не нужно
  удали ключ     — забыть ключ, вернуться к Википедии

Информация:
  время / дата                   — текущее время и дата
  характеристики                 — о вашем компьютере
  кто ты                         — немного обо мне

Разное:
  анекдот                        — поднять настроение
  очисти чат                     — очистить историю
  пока                           — завершить работу

Подсказка: длинные тексты (например, API-ключ) вставляйте Ctrl+V,
правой кнопкой мыши → «Вставить» или кнопкой «Вставить» у поля ввода —
это работает при любой раскладке клавиатуры. Можно и без копирования:
напишите «ключ из файла» и выберите txt-файл с ключом.
Стрелки вверх/вниз в поле ввода листают историю ваших команд.
Правая кнопка мыши на сообщении копирует его текст.

Пишите как удобно: я понимаю опечатки («загугли пагоду»),
разные формулировки и разговорные варианты команд."""

# ----- английские версии больших текстов (v7.1) -----
GREETINGS_EN = [
    'Hello! How can I help? For the command list, type "help".',
    'Hi there! I am online. What shall we do?',
    'Hey! Listening to you.',
    'Hello! Ready to work.',
]

THANKS_REPLIES_EN = ['Anytime!', 'My pleasure!', 'Glad to help.']

JOKES_EN = [
    'A programmer sets two glasses by the bed at night: a full one — '
    'in case they get thirsty, and an empty one — in case they do not.',
    'An optimist says the glass is half full. A pessimist: half empty. '
    'A programmer: the glass is twice as big as it needs to be.',
    'There are two kinds of people: those who make backups, '
    'and those who have never lost data.',
    '— Honey, go buy a loaf of bread. If they have eggs, get a dozen. '
    'The programmer came back with twelve loaves.',
    'A kid asks a programmer: — Dad, why does the sun come up every morning? '
    '— Good question. Somebody probably set up an autostart.',
    '— Why do programmers dislike nature? — Too many bugs.',
    'A computer works perfectly right up to the moment '
    'you have to show the result to the boss.',
]

WHO_TEXT_EN = (
    'I am RotoGo Beryllium v%s — an offline assistant for your computer.\n'
    'I can open apps and sites (including searching for installed ones '
    'via Start-menu shortcuts), search Google, show weather and currency '
    'rates right in the chat, calculate expressions and percentages, set '
    'timers, translate, create folders, .txt/.docx documents, real .pptx '
    'presentations and .xlsx spreadsheets, take notes, find files, show '
    'the time, date and computer specs.\n'
    'I understand typos and varied phrasing. Command list — "help".'
) % APP_VERSION

HELP_TEXT_EN = """WHAT I CAN DO (v7 FINAL)

Mini-apps right in the chat:
  weather [in city]              — temperature, wind, humidity in chat
  rates [usd|eur|cny]            — Central Bank rates with daily change
  calculate 2+2*10 / 15% of 200  — calculator (+ - * / ^ % and parentheses)
  timer for 5 minutes            — I will remind you with a window, bubble and sound
  translate <text>               — Gemini or Google Translate
  coin / dice                    — a moment of randomness

Search and the web:
  google <query>                 — Google search
  open <app or site>             — notepad, roblox, steam, youtube...;
                                    unknown apps are searched
                                    via Start-menu shortcuts
  open folder <name>             — open a folder in Explorer

Files and documents:
  create folder <name>           — you can add "on desktop"
  create text document about <topic> — .txt with real text;
                                    you can add "in folder/in <name>"
  create document (word) about <topic> — .docx for Word, with headings
  make presentation about <topic> — a real .pptx with facts and photos;
                                    you can add "in folder/in <name>" and "10 slides"
  make spreadsheet about <topic> — a real .xlsx (Excel): header row,
                                    autofilter, frozen header row
  take note <text>               — a short .txt note on the desktop
  find file <name>               — search the desktop, Documents, Downloads
  open file <name>               — find and open right away

Text for presentations, documents and spreadsheets is written (in order,
whichever works first):
  1. Google Gemini (flash series; the working model is remembered) —
     if a key is connected; it also helps understand unusual phrasings
     and translates;
  2. Wikipedia — real facts and photos on the topic, no keys needed;
  3. the built-in knowledge base — works even without internet.
  Photos are searched in 5 sources IN PARALLEL: English and Russian
  Wikipedia, Wikimedia Commons, Openverse, Flickr.
  connect google  — paste a Gemini API key (aistudio.google.com,
                    "Get API key" button); the key stays only on your machine
  key from file   — pick a txt file with the key, no copying needed
  remove key      — forget the key, fall back to Wikipedia

Information:
  time / date                    — current time and date
  specs                          — about your computer
  who are you                    — a bit about me

Misc:
  joke                           — cheer you up
  clear chat                     — clear the history
  bye                            — quit

Language:
  english / russian / language   — switch the interface language (RU/EN)

Tip: paste long text (e.g. an API key) with Ctrl+V,
right-click → "Paste", or the "Paste" button next to the input field —
this works under any keyboard layout. You can also skip copying:
type "key from file" and pick a txt file with the key.
Up/Down arrows in the input field scroll through your command history.
Right-click on a message copies its text.

Type however you like: I understand typos ("google weathr"),
different phrasings and conversational variants of commands."""

CANCEL_WORDS = ('отмена', 'не надо', 'отмени', 'стоп', 'пропусти', 'неважно',
                'cancel', 'never mind', 'stop', 'skip', 'abort', 'forget it')

# ----------------------------------------------------------------------------
# v7: мини-приложения — погода, курсы, калькулятор, таймер, монетка/кубик
# ----------------------------------------------------------------------------

WEATHER_CODES = {
    0: ('Ясно', '☀'), 1: ('Преимущественно ясно', '🌤'),
    2: ('Переменная облачность', '⛅'), 3: ('Облачно', '☁'),
    45: ('Туман', '🌫'), 48: ('Изморозь', '🌫'),
    51: ('Слабая морось', '🌦'), 53: ('Морось', '🌦'),
    55: ('Сильная морось', '🌧'), 61: ('Слабый дождь', '🌦'),
    63: ('Дождь', '🌧'), 65: ('Сильный дождь', '🌧'),
    71: ('Слабый снег', '🌨'), 73: ('Снег', '❄'),
    75: ('Сильный снег', '❄'), 77: ('Снежные зёрна', '🌨'),
    80: ('Ливень', '🌧'), 81: ('Ливень', '🌧'),
    82: ('Сильный ливень', '⛈'), 85: ('Снежный ливень', '🌨'),
    86: ('Сильный снежный ливень', '❄'),
    95: ('Гроза', '⛈'), 96: ('Гроза с градом', '⛈'),
    99: ('Сильная гроза с градом', '⛈'),
}

# ============================================================================
# i18n: переключатель языка RU/EN (v7.1). Один бинарник — два языка.
#   LANG = 'ru' | 'en', хранится в lang.txt рядом с программой.
#   _tr(s) переводит фрагменты русских строк на английский, когда LANG=='en';
#   применяется на «выходе» (в add_msg), поэтому трогать ~80 мест выдачи не нужно.
#   Большие тексты (HELP/WHO/GREETINGS/JOKES) выбираются по LANG в cmd_*.
#   Wikipedia и промпты Gemini тоже переключаются по LANG.
# ============================================================================
_LANG_FILE = 'lang.txt'
LANG = 'ru'           # 'ru' или 'en'; реальное значение ставит _load_lang()
_on_lang_change = None  # колбэк GUI: перерисовать шапку/чипы/welcome после смены


def _load_lang():
    """Читает язык из lang.txt (если файла нет — по умолчанию 'ru')."""
    global LANG, _WIKI_API
    try:
        with open(os.path.join(_script_dir(), _LANG_FILE),
                  encoding='utf-8') as f:
            v = f.read().strip().lower()
        if v in ('ru', 'en'):
            LANG = v
    except Exception:
        LANG = 'ru'
    # синхронизируем Wikipedia API с выбранным языком
    _WIKI_API = ('https://en.wikipedia.org/w/api.php' if LANG == 'en'
                 else 'https://ru.wikipedia.org/w/api.php')


def set_lang(lang, refresh=True):
    """Сменить язык и сохранить выбор. lang: 'ru'|'en'|'toggle'|'en'/'english'..."""
    global LANG
    if isinstance(lang, str):
        s = lang.strip().lower()
    else:
        s = ''
    if s in ('toggle', 'switch', 'переключ', 'переключи', 'сменить', 'сменя'):
        new = 'en' if LANG != 'en' else 'ru'
    elif s.startswith(('en', 'eng', 'english', 'англ', 'английск')):
        new = 'en'
    elif s.startswith(('ru', 'rus', 'russian', 'рус', 'русск')):
        new = 'ru'
    else:
        new = LANG
    LANG = new
    try:
        with open(os.path.join(_script_dir(), _LANG_FILE), 'w',
                  encoding='utf-8') as f:
            f.write(new)
    except Exception:
        pass
    # Wikipedia API переключается по языку (en.wikipedia.org для EN)
    global _WIKI_API
    try:
        if new == 'en':
            _WIKI_API = 'https://en.wikipedia.org/w/api.php'
        else:
            _WIKI_API = 'https://ru.wikipedia.org/w/api.php'
    except Exception:
        pass
    if refresh and _on_lang_change:
        try:
            _on_lang_change()
        except Exception:
            pass
    return new


def _gp(ru, en):
    """Промпт для Gemini по текущему языку."""
    return en if LANG == 'en' else ru


# Английские примеры команд для подсказки «возможно, вы имели в виду …?»
_EXAMPLE_EN = {
    'посчитай 2+2*10': 'calculate 2+2*10',
    'загугли погоду': 'google the weather',
    'открой блокнот': 'open notepad',
    'открой папку работы': 'open work folder',
    'погода': 'weather',
    'курс доллара': 'exchange rates',
    'таймер на 5 минут': 'timer for 5 minutes',
    'переведи hello world': 'translate hello world',
    'создай таблицу про цены': 'make a spreadsheet about prices',
    'найди файл отчет': 'find file report',
    'монетка': 'coin flip',
    'создай папку работы': 'create work folder',
    'создай презентацию про космос': 'make a presentation about space',
    'создай текстовый документ про AI': 'create a text document about AI',
    'подключи гугл': 'connect google',
    'запиши заметку купить хлеб': 'take a note buy bread',
    'помощь': 'help',
    'время': 'time',
    'дата': 'date',
    'анекдот': 'joke',
    'характеристики': 'system info',
    'кто ты': 'who are you',
    'спасибо': 'thanks',
    'привет': 'hello',
    'очисти чат': 'clear chat',
    'пока': 'bye',
}

# -- таблица перевода фрагментов (применяется в EN-режиме). Порядок важен:
#    более длинные/специфичные строки — раньше, чтобы не подменять их части. --
_TR_PAIRS = [
    # --- время / дата (вместе с WEEKDAYS/MONTHS ниже добивают до английского) ---
    ('Сейчас ', "It's "),
    ('Сегодня ', 'Today is '),
    (' года.', '.'),
    # --- помощь / «кто ты» / приветствия / шутки / благодарности ---
    # (HELP_TEXT, WHO_TEXT, GREETINGS, JOKES, THANKS_REPLIES выбираются по LANG
    #  прямо в cmd_*, поэтому здесь только сопутствующие фразы) ---
    ('Напишите «помощь» — покажу все команды.',
     'Type "help" to see all commands.'),
    ('Напишите «помощь» — покажу все команды.',
     'Type "help" to see all commands.'),
    ('Напишите команду. Список — «помощь».',
     'Type a command. List — "help".'),
    ('Не понял команду: «%s».', 'Did not understand the command: "%s".'),
    ('Возможно, вы имели в виду «%s»?', 'Did you mean "%s"?'),
    # --- общие ответы об успехе/ошибке ---
    ('Готово! Презентация создана и проверена на диске.',
     'Done! Presentation created and verified on disk.'),
    ('Готово! Таблица создана и проверена на диске.',
     'Done! Spreadsheet created and verified on disk.'),
    ('Готово! Документ создан и проверен на диске.',
     'Done! Document created and verified on disk.'),
    ('Готово! Заметка сохранена: %s', 'Done! Note saved: %s'),
    ('Готово: поиск открыт в браузере.', 'Done: search opened in the browser.'),
    ('Готово: погода открыта в браузере.', 'Done: weather opened in the browser.'),
    ('Готово: открыл в браузере.', 'Done: opened in the browser.'),
    ('Готово: запустил.', 'Done: launched.'),
    ('Готово: папка открыта в Проводнике.', 'Done: folder opened in Explorer.'),
    ('Готово: папка открыта.', 'Done: folder opened.'),
    ('Не удалось открыть браузер.', 'Could not open the browser.'),
    ('Не удалось открыть браузер и погоду.',
     'Could not open the browser for weather.'),
    ('Не удалось открыть переводчик.', 'Could not open the translator.'),
    ('Не удалось открыть папку: %s', 'Could not open the folder: %s'),
    ('Не удалось создать папку: %s', 'Could not create the folder: %s'),
    ('Не удалось создать таблицу: %s', 'Could not create the spreadsheet: %s'),
    ('Не удалось создать презентацию: %s',
     'Could not create the presentation: %s'),
    ('Не удалось создать документ: %s', 'Could not create the document: %s'),
    ('Не удалось сохранить заметку: %s', 'Could not save the note: %s'),
    ('Не удалось сохранить ключ: %s', 'Could not save the key: %s'),
    ('Не удалось прочитать файл: %s', 'Could not read the file: %s'),
    ('Не удалось запустить «%s» (%s).', 'Could not launch "%s" (%s).'),
    ('Не удалось открыть: %s', 'Could not open: %s'),
    ('Запуск программ доступен только на Windows.',
     'Launching apps is only available on Windows.'),
    ('Файл НЕ создан — это честный отчёт об ошибке.',
     'File NOT created — this is an honest error report.'),
    ('Файл НЕ создан — это честный отчёт об ошибке, а не выдуманный успех.',
     'File NOT created — this is an honest error report, not a fake success.'),
    ('Файл не записался на диск — таблица НЕ создана.',
     'File was not written to disk — spreadsheet NOT created.'),
    ('Файл не записался на диск — презентация НЕ создана.',
     'File was not written to disk — presentation NOT created.'),
    ('Файл не записался на диск — документ НЕ создан.',
     'File was not written to disk — document NOT created.'),
    ('Заметка не записалась на диск.', 'Note was not written to disk.'),
    ('Внутренняя проблема: таймер недоступен в этом режиме.',
     'Internal problem: timer is unavailable in this mode.'),
    ('Извините, произошла внутренняя ошибка: %s',
     'Sorry, an internal error occurred: %s'),
    # --- поиск / браузер ---
    ('Ищу в Google: «%s»...', 'Searching Google: "%s"...'),
    ('Что найти? Напишите, например: «загугли погоду».',
     'What to search? Example: "google the weather".'),
    ('Отменить — «отмена».', 'Cancel — "cancel".'),
    ('Открываю в браузере: %s...', 'Opening in the browser: %s...'),
    ('Запускаю: %s...', 'Launching: %s...'),
    ('Открываю: %s', 'Opening: %s'),
    ('Открываю папку: %s', 'Opening folder: %s'),
    # --- погода ---
    ('Узнаю погоду в вашем городе…', 'Fetching weather for your location…'),
    ('Узнаю погоду для «', 'Fetching weather for "'),
    ('Не получилось собрать погоду в чат — открываю сайт…',
     'Could not assemble weather in chat — opening the site…'),
    ('Источник: wttr.in и Open-Meteo (без ключей). '
     'Подробнее: «открой погоду» — сайт с графиками.',
     'Source: wttr.in and Open-Meteo (no keys). More: "open weather" for the chart site.'),
    ('ПОГОДА', 'WEATHER'),
    # --- курсы валют ---
    ('Беру свежие курсы ЦБ РФ…', 'Fetching fresh Central Bank rates…'),
    ('Курсы сейчас недоступны (нет сети или ЦБ молчит).',
     'Rates are unavailable right now (no network or the bank is silent).'),
    ('Открыл сайт ЦБ с таблицей курсов.',
     'Opened the Central Bank site with the rates table.'),
    ('КУРСЫ ЦБ РФ · ', 'CENTRAL BANK RATES · '),
    ('Кэш 10 минут — «курс» обновит при необходимости. '
     'Все валюты: cbr-xml-daily.ru',
     'Cached for 10 minutes — "rates" refreshes when needed. '
     'All currencies: cbr-xml-daily.ru'),
    ('Доллар США', 'US Dollar'), ('Евро', 'Euro'), ('Юань', 'Yuan'),
    ('Фунт стерлингов', 'Pound Sterling'), ('Дирхам ОАЭ', 'UAE Dirham'),
    ('Турецкая лира', 'Turkish Lira'), ('Тенге', 'Tenge'), ('Иена', 'Yen'),
    # --- калькулятор ---
    ('Что посчитать? Напишите пример.', 'What to calculate? Type an expression.'),
    ('Понял проценты, но нужно «от чего»: напишите например «15% от 200».',
     'Got percentages, but need "of what": e.g. "15% of 200".'),
    ('Не смог вычислить «%s».', 'Could not evaluate "%s".'),
    ('Понимаю: + - * / ^ (степень), % (остаток), скобки, '
     'запятую-десятичную и «15% от 200».',
     'I understand: + - * / ^ (power), % (remainder), parentheses, '
     'decimal comma and "15% of 200".'),
    # --- таймер ---
    ('На сколько поставить таймер?',
     'How long should the timer be?'),
    ('Таймер запущен: %s. Напомню в чате, окном и звуком.',
     'Timer started: %s. I will remind you in chat, a window and a sound.'),
    ('Продолжаю слушать ваши команды — таймер идёт в фоне.',
     'Keep typing your commands — the timer runs in the background.'),
    ('Время вышло!', "Time's up!"),
    ('прошло ', 'elapsed '),
    ('Таймер — RotoGo Beryllium', 'Timer — RotoGo Beryllium'),
    # --- перевод ---
    ('Перевожу через Gemini…', 'Translating via Gemini…'),
    ('ПЕРЕВОД', 'TRANSLATION'),
    ('Открыл Google Переводчик с этим текстом.',
     'Opened Google Translate with this text.'),
    ('Что перевести? Напишите текст.', 'What to translate? Type the text.'),
    # --- монетка / кубик ---
    ('🎲 Кубик: %d', '🎲 Die: %d'),
    ('Случайное число: %d (из %d–%d)',
     'Random number: %d (of %d–%d)'),
    ('🪙  ОРЁЛ', '🪙  HEADS'), ('🪙  РЕШКА', '🪙  TAILS'),
    ('🪙 ОРЁЛ', '🪙  HEADS'), ('🪙 РЕШКА', '🪙  TAILS'),
    ('ОРЁЛ', 'HEADS'), ('РЕШКА', 'TAILS'),
    # --- поиск файлов ---
    ('Ищу «%s» на столе, в документах и загрузках…',
     'Searching for "%s" on the desktop, in Documents and Downloads…'),
    ('Нашёл %d:', 'Found %d:'),
    ('Файлов с «%s» не нашёл (искал на рабочем столе, '
     'в документах и загрузках, глубина 2).',
     'No files matching "%s" found (searched the desktop, Documents '
     'and Downloads, depth 2).'),
    ('Подсказка: скажите точнее имя или попросите '
     '«создай презентацию про …» — я сделаю файл сам.',
     'Tip: be more specific, or ask "make a presentation about …" — '
     'I will create the file myself.'),
    ('папка «', 'folder "'),
    ('Открыть первый — «открой файл %s».', 'Open the first one — "open file %s".'),
    # --- таблицы ---
    ('Собираю содержание и пишу таблицу…',
     'Gathering content and writing the spreadsheet…'),
    ('Про что сделать таблицу? Напишите тему.',
     'What should the spreadsheet be about? Type a topic.'),
    ('В таблице: шапка с заливкой и закреплена, автофильтр, '
     'ширины колонок под текст.',
     'In the spreadsheet: a filled header row (frozen), autofilter, '
     'column widths fit to text.'),
    ('Открой файл — Excel (или LibreOffice) покажет всё сразу.',
     'Open the file — Excel (or LibreOffice) shows it all at once.'),
    # --- презентации ---
    ('Пишу текст и структуру слайдов…', 'Writing slide text and structure…'),
    ('Текст готов — ищу фото в 5 источниках параллельно…',
     'Text ready — searching photos across 5 sources in parallel…'),
    ('Собираю слайды и записываю файл…',
     'Assembling slides and writing the file…'),
    ('На какую тему сделать презентацию? Напишите тему.',
     'What should the presentation be about? Type a topic.'),
    ('Открой файл и дополни под свою задачу — основа уже готова.',
     'Open the file and tailor it to your task — the base is ready.'),
    ('Просили %d слайдов — вышло %d (беру не больше 6 разделов).',
     'Requested %d slides — got %d (I take at most 6 sections).'),
    ('Открыть папку с файлом: «открой папку».',
     'Open the file folder: "open folder".'),
    ('Картинки: %d настоящих фото по теме (%s).',
     'Images: %d real photos on the topic (%s).'),
    ('Картинки: %d настоящих фото по теме (%s) '
     'и %d разделов без фото (там декоративный фон).',
     'Images: %d real photos on the topic (%s) and '
     '%d sections without photos (decorative background there).'),
    ('Картинки: %d декоративных фонов — настоящие '
     'фото в открытых источниках не нашлись или нет сети.',
     'Images: %d decorative backgrounds — no real photos found '
     'in open sources or no network.'),
    ('Википедия, Wikimedia Commons, Openverse, Flickr',
     'Wikipedia, Wikimedia Commons, Openverse, Flickr'),
    ('Gemini не сработал: %s. Подстраховался другим '
     'источником — см. строку «Текст». Проверить ключ: '
     '«подключи гугл».',
     'Gemini did not work: %s. Fell back to another source — '
     'see the "Text" line. Check the key: "connect google".'),
    # --- документы ---
    ('О чём написать документ? Напишите тему.',
     'What should the document be about? Type a topic.'),
    ('Открой файл — основа уже готова, дополняйте под себя.',
     'Open the file — the base is ready, tailor it to your needs.'),
    # --- папки ---
    ('Как назвать папку? Напишите имя.', 'What to name the folder? Type a name.'),
    ('В имени папки нельзя использовать символы: \\ / : * ? " < > |',
     'Folder name cannot contain: \\ / : * ? " < > |'),
    ('Папка уже существует: %s', 'Folder already exists: %s'),
    ('Не удалось создать папку. Проверьте имя и права доступа.',
     'Could not create the folder. Check the name and permissions.'),
    ('Не нашёл папку «%s». Проверьте имя.',
     'Folder "%s" not found. Check the name.'),
    # --- api key ---
    ('Ключ удалён. Текст для презентаций беру из Википедии '
     'и встроенной базы знаний.',
     'Key removed. Presentation text comes from Wikipedia '
     'and the built-in knowledge base.'),
    ('Ключа и так нет — использую Википедию и встроенную базу.',
     'No key anyway — using Wikipedia and the built-in base.'),
    ('Ключ Gemini уже подключён (%s…).',
     'Gemini key already connected (%s…).'),
    ('Ключ сохранён в gemini_key.txt рядом с программой — '
     'он не уходит с компьютера.',
     'Key saved to gemini_key.txt next to the program — '
     'it never leaves your computer.'),
    ('Теперь текст презентаций пишет Google Gemini. '
     'Проверьте: «сделай презентацию про космос».',
     'Now Google Gemini writes the presentation text. '
     'Test it: "make a presentation about space".'),
    ('Внимание: ключи Gemini начинаются с «AIza…» или «AQ.…». '
     'Если генерация не заработает — проверьте ключ в '
     'aistudio.google.com; я подстрахуюсь Википедией.',
     'Note: Gemini keys start with "AIza…" or "AQ.…". '
     'If generation does not work — check the key at '
     'aistudio.google.com; I will fall back to Wikipedia.'),
    ('Пришлите API-ключ Gemini одним сообщением '
     '(можно вставить: Ctrl+V или правая кнопка мыши '
     '→ «Вставить»; или напишите «ключ из файла»).',
     'Send the Gemini API key in one message '
     '(paste: Ctrl+V or right-click → "Paste"; '
     'or type "key from file").'),
    ('Бесплатный ключ: aistudio.google.com → «Get API key» '
     '(начинается с AIza или AQ.). Отменить — «отмена».',
     'Free key: aistudio.google.com → "Get API key" '
     '(starts with AIza or AQ.). Cancel — "cancel".'),
    ('Файл не выбран — ключ не менялся.', 'No file selected — key unchanged.'),
    ('В файле не похоже на ключ: нужна ОДНА строка не короче '
     '16 символов без пробелов (AIza… или AQ.…).',
     'The file does not look like a key: need ONE line at least '
     '16 characters with no spaces (AIza… or AQ.…).'),
    ('Выберите файл с API-ключом', 'Select the file with the API key'),
    # --- заметки ---
    ('Что записать в заметку? Напишите текст.',
     'What to write in the note? Type the text.'),
    ('Заметка · ', 'Note · '),
    # --- открытие приложений/сайтов ---
    ('Что открыть?', 'What to open?'),
    ('Не нашёл на этом компьютере приложение или сайт «%s».',
     'Could not find an app or site "%s" on this computer.'),
    ('Ближайшие из известных: %s.', 'Closest known ones: %s.'),
    ('Подсказка: установленную программу можно назвать как '
     'в меню «Пуск» — я умею её искать. Известные мне: %s.',
     'Tip: an installed app can be named as in the Start menu — '
     'I can search for it. Known to me: %s.'),
    ('Нашёл программу «%s» в меню «Пуск» — запускаю...',
     'Found the app "%s" in the Start menu — launching...'),
    # --- системная информация ---
    ('ХАРАКТЕРИСТИКИ КОМПЬЮТЕРА', 'COMPUTER SPECIFICATIONS'),
    ('ОС:', 'OS:'), ('Процессор:', 'CPU:'), ('Ядер:', 'Cores:'),
    ('ОЗУ:', 'RAM:'), ('Диск ', 'Disk '), ('всего ', 'total '),
    ('свободно ', 'free '), ('не определён', 'not detected'),
    # --- выход / очистка ---
    ('До встречи! Окно закроется через пару секунд.',
     'See you! The window will close in a few seconds.'),
    ('Хорошо, отменил.', 'Okay, cancelled.'),
    # --- уточняющие вопросы (общие «например»-подсказки) ---
    ('Например: «загугли погоду».', 'Example: "google the weather".'),
    ('Например: «открой блокнот», «открой роблокс», «открой ютуб».',
     'Example: "open notepad", "open roblox", "open youtube".'),
    ('Например: «посчитай 2+2*10», «сколько будет 15% от 200».',
     'Example: "calculate 2+2*10", "how much is 15% of 200".'),
    ('Например: «таймер на 5 минут», «напомни через 30 секунд».',
     'Example: "timer for 5 minutes", "remind me in 30 seconds".'),
    ('Например: «переведи hello world».', 'Example: "translate hello world".'),
    ('Например: «найди файл отчет».', 'Example: "find file report".'),
    ('Например: «создай таблицу про космос».',
     'Example: "make a spreadsheet about space".'),
    ('Например: «про космос» или «искусственный интеллект». '
     'Можно добавить «на 10 слайдов».',
     'Example: "about space" or "artificial intelligence". '
     'You can add "10 slides".'),
    ('Например: «про искусственный интеллект».',
     'Example: "about artificial intelligence".'),
    ('Например: «мои работы».', 'Example: "my work".'),
    ('Что открыть? Напишите, например: «открой блокнот».',
     'What to open? Example: "open notepad".'),
    # --- дни недели и месяцы (добавляются в форматированные даты/время) ---
    ('понедельник', 'Monday'), ('вторник', 'Tuesday'),
    ('среда', 'Wednesday'), ('четверг', 'Thursday'),
    ('пятница', 'Friday'), ('суббота', 'Saturday'),
    ('воскресенье', 'Sunday'),
    ('января', 'January'), ('февраля', 'February'), ('марта', 'March'),
    ('апреля', 'April'), ('мая', 'May'), ('июня', 'June'),
    ('июля', 'July'), ('августа', 'August'), ('сентября', 'September'),
    ('октября', 'October'), ('ноября', 'November'), ('декабря', 'December'),
    # --- коды погоды (метки) ---
    ('Сильная гроза с градом', 'Severe thunderstorm with hail'),
    ('Гроза с градом', 'Thunderstorm with hail'),
    ('Сильный снежный ливень', 'Heavy snow shower'),
    ('Снежный ливень', 'Snow shower'),
    ('Сильный ливень', 'Heavy shower'),
    ('Снежные зёрна', 'Snow grains'),
    ('Преимущественно ясно', 'Mostly clear'),
    ('Переменная облачность', 'Partly cloudy'),
    ('Сильная морось', 'Heavy drizzle'),
    ('Слабая морось', 'Light drizzle'),
    ('Сильный дождь', 'Heavy rain'),
    ('Слабый дождь', 'Light rain'),
    ('Сильный снег', 'Heavy snow'),
    ('Слабый снег', 'Light snow'),
    ('Гроза', 'Thunderstorm'), ('Ливень', 'Shower'), ('Туман', 'Fog'),
    ('Изморозь', 'Rime frost'), ('Морось', 'Drizzle'), ('Дождь', 'Rain'),
    ('Снег', 'Snow'), ('Облачно', 'Cloudy'), ('Ясно', 'Clear'),
    # --- язык: подтверждения переключения ---
    ('Язык переключен на русский.', 'Language switched to Russian.'),
    ('Язык переключен на английский.', 'Language switched to English.'),
    # --- кавычки-ёлочки → прямые (в EN-режиме выглядят привычнее) ---
    ('«', '"'), ('»', '"'),
]


def _compile_tr():
    """Компилируем _TR_PAIRS в regex-шаблоны.
    Пары с %s/%d становятся шаблонами с группами-захватами (матчат
    отформатированный вывод, где %s уже подставлен реальным значением).
    Пары без % — обычные литералы. Сортируем по длине ключа убыванием,
    чтобы специфичные (длинные) шаблоны применялись раньше коротких
    (особенно « » -> " " в самом конце)."""
    import re as _re
    pats = []
    for ru, en in sorted(_TR_PAIRS, key=lambda p: len(p[0]), reverse=True):
        ru_parts = _re.split(r'(%[sdf])', ru)
        rx = ''.join(
            _re.escape(p) if not (len(p) == 2 and p[0] == '%') else
            (r'(.*?)' if p == '%s' else r'(\d+(?:[.,]\d+)?)')
            for p in ru_parts)
        n = 0
        rp = ''
        for p in _re.split(r'(%[sdf])', en):
            if len(p) == 2 and p[0] == '%':
                n += 1
                rp += r'\%d' % n
            else:
                rp += p.replace('\\', r'\\')
        pats.append((_re.compile(rx), rp))
    return pats


_TR_PATS = None


def _tr(s):
    """Перевести строку по таблице _TR_PAIRS, если включён английский.
    Применяется к уже отформатированному выводу (значения подставлены)."""
    global _TR_PATS
    if LANG != 'en' or not s:
        return s
    if _TR_PATS is None:
        _TR_PATS = _compile_tr()
    out = s
    for rx, rp in _TR_PATS:
        if rx.search(out):
            out = rx.sub(rp, out)
    return out


# что пользователь может назвать — находим в wttr.in через поиск Open-Meteo
_GEO_CACHE = {'city': {}, 'ts': 0.0}
_WEATHER_CACHE = {'key': None, 'ts': 0.0, 'data': None}
_CBR_CACHE = {'ts': 0.0, 'data': None}


def _wind_dir(deg):
    dirs = ('С', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ')
    try:
        return dirs[int((float(deg) % 360) / 45)]
    except Exception:
        return ''


def fetch_weather(city=None):
    """Погода прямо в чат. -> (строки_пузыря, город) | None (сеть/сбой).

    wttr.in отдаёт русский JSON с текущей погодой; город (если назван)
    находим гео-поиском Open-Meteo (без ключа). Кэш на 10 минут."""
    if not net_available():
        return None
    now = time.time()
    key = (city or '').lower().strip()
    if _WEATHER_CACHE['data'] and now - _WEATHER_CACHE['ts'] < 600 \
            and _WEATHER_CACHE['key'] == key:
        return _WEATHER_CACHE['data']
    place = ''
    try:
        if city:
            # города в латиницу: гео-поиск Open-Meteo понимает и кириллицу
            try:
                geo = _http_json('https://geocoding-api.open-meteo.com/v1/'
                                 'search?count=1&language=ru&name='
                                 + urllib.parse.quote(city), timeout=8)
                res = ((geo.get('results') or [None])[0]) or {}
                lat, lon = res.get('latitude'), res.get('longitude')
                place = res.get('name') or city
            except Exception:
                lat = lon = None
            if lat is None:
                return ('МЕСТО', city), None   # город не нашли
            url = ('https://wttr.in/%s,%s?format=j1&lang=ru'
                   % (urllib.parse.quote(str(lat)), urllib.parse.quote(str(lon))))
        else:
            url = 'https://wttr.in/?format=j1&lang=ru'
        data = _http_json(url, timeout=12)
        cur = (data.get('current_condition') or [{}])[0]
        w = (cur.get('weatherDesc') or [{}])[0].get('value') or ''
        try:
            area = (data.get('nearest_area') or [{}])[0]
            place = place or (area.get('areaName') or [{}])[0].get('value') or ''
            country = (area.get('country') or [{}])[0].get('value') or ''
        except Exception:
            country = ''
        # код погоды -> русское описание и смайл
        code = None
        try:
            code = int(cur.get('weatherCode') or -1)
        except Exception:
            pass
        desc, smile = WEATHER_CODES.get(code, (w or 'Погода', ''))
        temp = cur.get('temp_C')
        feels = cur.get('FeelsLikeC')
        hum = cur.get('humidity')
        wind = cur.get('windspeedKmph')
        wdir = _wind_dir(cur.get('winddirDegree') or 0)
        try:
            pres = str(cur.get('pressure')).replace('.', ',')
        except Exception:
            pres = ''
        vis = cur.get('visibility')
        uv = cur.get('uvIndex')
        lines = ['%s  %s' % (smile, desc) if smile else desc]
        where = ' '.join(x for x in (place, country) if x)
        if where:
            lines.append('Где: %s' % where)
        lines.append('Температура: %s °C (ощущается как %s)'
                     % (temp, feels))
        if wind:
            lines.append('Ветер: %s км/ч%s' % (wind,
                          (', ' + wdir) if wdir else ''))
        if hum:
            lines.append('Влажность: %s%%' % hum)
        extra = []
        try:
            if vis:
                extra.append('видимость %s км' % vis)
            if uv:
                extra.append('УФ-индекс %s' % uv)
        except Exception:
            pass
        if extra:
            lines.append('Ещё: ' + ', '.join(extra))
        today = None
        try:
            today = (data.get('weather') or [{}])[0]
        except Exception:
            pass
        if today:
            try:
                lines.append('Сегодня: %s…%s °C'
                             % (today['mintempC'], today['maxtempC']))
            except Exception:
                pass
        out = (lines, place or where)
        _WEATHER_CACHE.update(key=key, ts=now, data=out)
        return out
    except Exception as e:
        log('Погода: %r' % e)
        return None


def fetch_rates():
    """Курсы валют ЦБ РФ. -> (строки, дата) | None. Кэш 10 минут."""
    if not net_available():
        return None
    if _CBR_CACHE['data'] and time.time() - _CBR_CACHE['ts'] < 600:
        return _CBR_CACHE['data']
    try:
        data = _http_json('https://www.cbr-xml-daily.ru/daily_json.js',
                          timeout=12)
        d = data.get('Date', '')
        m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', d)
        date_str = ('%s.%s.%s' % (m.group(1), m.group(2), m.group(3))) if m \
            else d[:10]
        lines = []
        for code, name in (('USD', 'Доллар США'), ('EUR', 'Евро'),
                           ('CNY', 'Юань'), ('GBP', 'Фунт стерлингов'),
                           ('AED', 'Дирхам ОАЭ'), ('TRY', 'Турецкая лира'),
                           ('KZT', 'Тенге'), ('JPY', 'Иена')):
            v = (data.get('Valute') or {}).get(code)
            if not v:
                continue
            cur = float(v['Value'])
            prev = float(v.get('Previous') or cur)
            nom = int(v.get('Nominal') or 1)
            if nom != 1:
                cur /= nom
                prev /= nom
            diff = cur - prev
            sign = '+' if diff > 0 else ''
            if abs(diff) < 0.0001:
                chg = 'без изменений'
            else:
                chg = '%s%.2f %s' % (sign, abs(diff),
                                     'руб.' if abs(diff) >= 0.01 else 'коп.')
                chg = ('▲ ' if diff > 0 else '▼ ') + chg
            lines.append('%s: %s %s  ·  %s'
                         % (name, ('%.2f' % cur).replace('.', ','), 'руб.', chg))
        out = (lines, date_str)
        _CBR_CACHE.update(ts=time.time(), data=out)
        return out
    except Exception as e:
        log('Курсы ЦБ: %r' % e)
        return None


_ALLOWED_CALC = set('0123456789+-*/().,^% ')


def _calc_replace_percent(expr):
    """«15% от 200» и «10 + 5%» -> обычная запись для вычислителя."""
    e = expr.strip()
    m = re.match(r'^\s*([\d.,]+)\s*%\s*от\s*([\d.,]+)\s*$', e, re.I)
    if m:
        return '%s / 100 * %s' % (m.group(1), m.group(2))
    m = re.match(r'^\s*([\d.,]+)\s*%\s*$', e)
    if m:
        return None   # просто процент без числа — не понятно от чего
    e = re.sub(r'\s+', '', e).replace(',', '.')
    # «10 + 5%» — процент от первого числа в выражении (бытовой смысл)
    m = re.match(r'^([\d.]+)\s*([+\-])\s*([\d.]+)%$', e)
    if m and m.group(2) == '+':
        return '(%s + %s / 100 * %s)' % (m.group(1), m.group(3), m.group(1))
    if m and m.group(2) == '-':
        return '(%s - %s / 100 * %s)' % (m.group(1), m.group(3), m.group(1))
    return e


def calc_expr(expr):
    """Безопасный калькулятор. -> (результат_str, подробный_str) | None.

    Только цифры и + - * / ^ % ( ); вычисление через ast с проверкой
    каждого узла — никаких eval на пользовательских данных."""
    expr = (expr or '').strip()
    if not expr or not re.search(r'\d', expr):
        return None
    if not set(expr) <= _ALLOWED_CALC:
        # внутри может быть русское «15% от 200» — вытянем чистую часть
        m = re.match(r'^\s*([\d.,]+\s*%\s*от\s*[\d.,]+)\s*$', expr, re.I)
        if not m:
            return None
        expr = m.group(1)
    e = _calc_replace_percent(expr)
    if e is None:
        return None
    if not re.search(r'[+\-*/^%]', e):
        return None
    try:
        e2 = e.replace('^', '**')
        tree = ast.parse(e2.replace('**', '#').replace('*', '@')
                         .replace('#', '**').replace('@', '*'),
                         mode='eval')
    except Exception:
        return None

    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            a, b = _ev(node.left), _ev(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                return a + b
            if isinstance(op, ast.Sub):
                return a - b
            if isinstance(op, ast.Mult):
                return a * b
            if isinstance(op, ast.Div):
                if b == 0:
                    raise ZeroDivisionError
                return a / b
            if isinstance(op, ast.Pow):
                if abs(b) > 64:
                    raise OverflowError
                return a ** b
            if isinstance(op, ast.Mod):
                if b == 0:
                    raise ZeroDivisionError
                return a % b
            raise ValueError
        if isinstance(node, ast.UnaryOp):
            v = _ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else +v
        raise ValueError

    try:
        val = _ev(tree)
    except Exception:
        return None
    if isinstance(val, complex):
        return None
    if math.isinf(val) or math.isnan(val):
        return None
    pretty = ('%s = %s' % (expr, _fmt_num(val)))
    return _fmt_num(val), pretty


def _fmt_num(v):
    """Число к красивой строке: без хвостовых нулей, с пробелами тысяч."""
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = ('%f' % v).rstrip('0').rstrip('.') if isinstance(v, float) else str(v)
    neg = s.startswith('-')
    s = s.lstrip('-')
    if '.' in s:
        ip, fp = s.split('.')
    else:
        ip, fp = s, ''
    groups = []
    while ip:
        groups.insert(0, ip[-3:])
        ip = ip[:-3]
    ip = ' '.join(groups)
    out = ip + (',' + fp if fp else '')
    return ('-' if neg else '') + out


def parse_duration(raw):
    """«на 5 минут», «через 30 секунд», «на полтора часа» -> секунды | None."""
    t = normalize(raw)
    t = re.sub(r'^(напомни|таймер|засеки|поставь|установи|сделай)\s+', '', t)
    t = re.sub(r'^(через|на)\s+', '', t)
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(секунд\w*|минут\w*|час\w*|дня|день)?',
                  t)
    if m:
        num = float(m.group(1).replace(',', '.'))
        unit = m.group(2) or 'минут'
        if unit.startswith('секунд'):
            secs = num
        elif unit.startswith('минут'):
            secs = num * 60
        elif unit.startswith('час'):
            secs = num * 3600
        elif unit in ('дня', 'день'):
            secs = num * 86400
        else:
            secs = num * 60
        return int(min(max(secs, 3), 86400))
    words = {'полчаса': 1800, 'час': 3600, 'полтора часа': 5400,
             'минуту': 60, 'минутки': 60, 'пять минут': 300}
    for w, s in words.items():
        if w in t:
            return s
    return None


def _human_secs(secs):
    secs = int(secs)
    if secs < 60:
        return '%d сек.' % secs
    if secs < 3600:
        return '%d мин. %d сек.' % (secs // 60, secs % 60) if secs % 60 \
            else '%d мин.' % (secs // 60)
    return '%d ч. %d мин.' % (secs // 3600, (secs % 3600) // 60)


# ----------------------------------------------------------------------------
# Распознавание намерений (intents)
# ----------------------------------------------------------------------------

# Порядок важен: при равном счёте побеждает более длинная фраза,
# а при полном равенстве — более ранний интент в списке.
# action=True — команды-действия (глагол). Получают бонус при сравнении:
# «зогугли погоду» должно быть ПОИСКОМ, а не «погодой», даже если глагол
# написан с опечаткой (неидеальное совпадение глагола важнее точного объекта).
INTENTS = [
    {'name': 'calc', 'example': 'посчитай 2+2*10', 'action': True,
     'phrases': [('посчитай',), ('вычисли',), ('сколько', 'будет'),
                 ('чему', 'равно'), ('сколько', 'получится')]},
    {'name': 'search', 'example': 'загугли погоду', 'action': True,
     'phrases': [('загугли',), ('погугли',), ('гугли',), ('поищи',),
                 ('поиск',), ('нагугли',), ('загуглить',),
                 ('поищи', 'в', 'гугле'), ('найди', 'в', 'интернете')]},
    {'name': 'open_app', 'example': 'открой блокнот', 'action': True,
     'phrases': [('открой',), ('запусти',), ('включи',), ('открыть',),
                 ('запустить',), ('стартуй',)]},
    {'name': 'open_folder', 'example': 'открой папку работы', 'action': True,
     'phrases': [('открой', 'папку'), ('открыть', 'папку'), ('зайди', 'в', 'папку')]},
    {'name': 'weather', 'example': 'погода',
     'phrases': [('погода',), ('погоду',), ('погоды',), ('какая', 'погода'),
                 ('за', 'окном'), ('на', 'улице'),
                 ('температура', 'за', 'окном'), ('на', 'улице', 'холодно')]},
    {'name': 'rates', 'example': 'курс доллара',
     'phrases': [('курс',), ('курсы',)]},
    {'name': 'timer', 'example': 'таймер на 5 минут',
     'phrases': [('таймер',), ('напомни',), ('засеки',), ('будильник',),
                 ('поставь', 'таймер')]},
    {'name': 'translate', 'example': 'переведи hello world',
     'action': True,
     'phrases': [('переведи',), ('перевести',), ('перевод',),
                 ('переведи', 'на', 'русский'), ('переведи', 'на', 'английский')]},
    {'name': 'create_xlsx', 'example': 'создай таблицу про цены',
     'action': True,
     'phrases': [('создай', 'таблицу'), ('сделай', 'таблицу'),
                 ('сгенерируй', 'таблицу'), ('подготовь', 'таблицу'),
                 ('новая', 'таблица'), ('создай', 'excel'),
                 ('создай', 'ексель'), ('создай', 'xlsx'),
                 ('создай', 'эксель')],
     'pairs': [('создай сделай сгенерируй подготовь собери составь',
                'таблицу таблица таблицы excel эксель ексель xlsx')]},
    {'name': 'find_file', 'example': 'найди файл отчет',
     'action': True,
     'phrases': [('найди', 'файл'), ('поищи', 'файл'), ('ищи', 'файл'),
                 ('открой', 'файл'), ('найди', 'документ'),
                 ('открой', 'документ'), ('где', 'файл'),
                 ('найди', 'презентацию'), ('открой', 'презентацию'),
                 ('найди', 'таблицу'), ('открой', 'таблицу')]},
    {'name': 'coin_dice', 'example': 'монетка',
     'phrases': [('монетка',), ('монетку',), ('подбрось', 'монетку'),
                 ('орел', 'или', 'решка'), ('кубик',), ('кости',),
                 ('брось', 'кубик'), ('подбрось', 'кубик'),
                 ('случайное', 'число')]},
    {'name': 'create_folder', 'example': 'создай папку работы', 'action': True,
     'phrases': [('создай', 'папку'), ('сделай', 'папку'), ('новая', 'папка'),
                 ('создай', 'директорию'), ('создай', 'каталог'),
                 ('сделай', 'директорию')],
     'pairs': [('создай сделай сгенерируй', 'папку папке папка директорию каталог')]},
    {'name': 'create_presentation', 'example': 'создай презентацию про космос', 'action': True,
     'phrases': [('создай', 'презентацию'), ('сделай', 'презентацию'),
                 ('сгенерируй', 'презентацию'), ('подготовь', 'презентацию'),
                 ('новая', 'презентация'), ('сделай', 'презу'),
                 ('презентацию',), ('презентация',), ('презу',), ('слайды',)],
     'pairs': [('создай сделай сгенерируй подготовь собери',
                'презентацию презентация презентации презентаций презу презенташку слайды')]},
    {'name': 'create_file', 'example': 'создай текстовый документ про AI', 'action': True,
     'phrases': [('создай', 'текстовый', 'документ'), ('создай', 'текстовый', 'файл'),
                 ('сделай', 'текстовый', 'документ'), ('создай', 'текстовый', 'тхт'),
                 ('создай', 'текстовый', 'txt'), ('новый', 'текстовый', 'документ'),
                 ('текстовый', 'документ'), ('создай', 'ворд'), ('создай', 'word'),
                 ('создай', 'docx'), ('создай', 'документ'), ('создай', 'файл'),
                 ('сделай', 'документ'), ('сделай', 'файл'), ('создай', 'тхт'),
                 ('создай', 'txt')],
     'pairs': [('создай сделай сгенерируй подготовь набери напиши составь',
                'документ документа документу файл файла тхт txt ворд word '
                'docx текст текста реферат реферата статью статьи конспект '
                'конспекта')]},
    {'name': 'api_key', 'example': 'подключи гугл', 'action': True,
     'phrases': [('подключи', 'гугл'), ('подключи', 'апи'), ('подключи', 'api'),
                 ('добавь', 'ключ'), ('вставь', 'ключ'), ('введи', 'ключ'),
                 ('подключи', 'ключ'), ('гугл', 'ключ'), ('api', 'ключ'),
                 ('апи', 'ключ'), ('ключ', 'гемини'), ('ключ', 'gemini'),
                 ('удали', 'ключ'), ('забудь', 'ключ'), ('отключи', 'ключ'),
                 ('ключ',)]},
    {'name': 'note', 'example': 'запиши заметку купить хлеб', 'action': True,
     'phrases': [('запиши', 'заметку'), ('сделай', 'заметку'),
                 ('новая', 'заметка'), ('заметка',), ('запиши',)]},
    {'name': 'help', 'example': 'помощь',
     'phrases': [('помощь',), ('помоги',), ('команды',), ('хелп',), ('help',),
                 ('что', 'ты', 'умеешь'), ('список', 'команд'), ('умения',)]},
    {'name': 'time', 'example': 'время',
     'phrases': [('время',), ('времени',), ('который', 'час'),
                 ('сколько', 'времени')]},
    {'name': 'date', 'example': 'дата',
     'phrases': [('дата',), ('какое', 'число'), ('какой', 'сегодня', 'день'),
                 ('какое', 'сегодня', 'число')]},
    {'name': 'joke', 'example': 'анекдот',
     'phrases': [('анекдот',), ('шутка',), ('пошути',),
                 ('расскажи', 'анекдот'), ('расскажи', 'шутку'), ('смешное',)]},
    {'name': 'system', 'example': 'характеристики',
     'phrases': [('характеристики',), ('спецификации',), ('о', 'компьютере'),
                 ('о', 'пк'), ('информация', 'о', 'системе'),
                 ('сколько', 'оперативки'), ('оперативка',), ('озу',)]},
    {'name': 'who', 'example': 'кто ты',
     'phrases': [('кто', 'ты'), ('как', 'тебя', 'зовут'), ('ты', 'кто'),
                 ('что', 'ты', 'такое'), ('кто', 'ты', 'такой')]},
    {'name': 'thanks', 'example': 'спасибо',
     'phrases': [('спасибо',), ('спс',), ('благодарю',), ('пасиба',),
                 ('спасиба',), ('thanks',)]},
    {'name': 'greeting', 'example': 'привет',
     'phrases': [('привет',), ('здравствуй',), ('здравствуйте',),
                 ('добрый', 'день'), ('доброе', 'утро'), ('добрый', 'вечер'),
                 ('доброй', 'ночи'), ('хай',), ('ку',), ('салют',), ('здорово',)]},
    {'name': 'clear', 'example': 'очисти чат', 'action': True,
     'phrases': [('очисти', 'чат'), ('очистить', 'чат'), ('очисти', 'экран'),
                 ('очисти', 'историю'), ('очисти',)]},
    {'name': 'exit', 'example': 'пока', 'action': True,
     'phrases': [('пока',), ('выход',), ('закройся',), ('выключись',),
                 ('до', 'свидания'), ('отключись',), ('бай',), ('quit',), ('exit',)]},
    {'name': 'language', 'example': 'english', 'action': True,
     'phrases': [('язык',), ('переключи', 'язык'), ('смени', 'язык'),
                 ('english',), ('русский',), ('russian',), ('language',),
                 ('switch', 'language'), ('change', 'language'),
                 ('переключи', 'на', 'английский'),
                 ('переключи', 'на', 'русский'),
                 ('switch', 'to', 'english'), ('switch', 'to', 'russian')]},
]

# английские фразы-триггеры для команд (двуязычный ввод — v7.1)
_INTENTS_EN_PHRASES = {
    'calc': [('calculate',), ('compute',), ('how', 'much', 'is'),
             ('what', 'is'), ('evaluate',)],
    'search': [('google',), ('search',), ('look', 'up'), ('find', 'online'),
               ('web', 'search')],
    'open_app': [('open',), ('launch',), ('start',), ('run',)],
    'open_folder': [('open', 'folder'), ('open', 'directory')],
    'weather': [('weather',), ('temperature',), ('how', 'hot'),
                ('is', 'it', 'cold'), ('forecast',)],
    'rates': [('rates',), ('exchange', 'rate'), ('currency',)],
    'timer': [('timer',), ('remind', 'me'), ('set', 'timer'), ('alarm',)],
    'translate': [('translate',), ('translation',)],
    'create_xlsx': [('make', 'spreadsheet'), ('create', 'spreadsheet'),
                    ('make', 'a', 'spreadsheet'), ('create', 'a', 'spreadsheet'),
                    ('new', 'spreadsheet'), ('make', 'excel'),
                    ('create', 'excel'), ('make', 'an', 'excel'),
                    ('make', 'xlsx'), ('create', 'xlsx')],
    'find_file': [('find', 'file'), ('search', 'file'), ('open', 'file'),
                  ('find', 'document'), ('open', 'document'),
                  ('where', 'is', 'file'), ('find', 'presentation'),
                  ('open', 'presentation'), ('find', 'spreadsheet')],
    'coin_dice': [('coin',), ('coin', 'flip'), ('flip', 'coin'),
                  ('heads', 'or', 'tails'), ('dice',), ('die',),
                  ('roll', 'dice'), ('random', 'number')],
    'create_folder': [('create', 'folder'), ('make', 'folder'),
                      ('create', 'a', 'folder'), ('make', 'a', 'folder'),
                      ('new', 'folder'), ('create', 'directory')],
    'create_presentation': [('make', 'presentation'), ('create', 'presentation'),
                            ('make', 'a', 'presentation'),
                            ('create', 'a', 'presentation'),
                            ('new', 'presentation'), ('make', 'slides'),
                            ('presentation',), ('slides',)],
    'create_file': [('create', 'text', 'document'), ('make', 'text', 'document'),
                    ('create', 'a', 'text', 'document'),
                    ('make', 'a', 'text', 'document'),
                    ('create', 'text', 'file'), ('new', 'text', 'document'),
                    ('text', 'document'), ('create', 'word'),
                    ('create', 'docx'), ('create', 'document'),
                    ('create', 'a', 'document'), ('make', 'a', 'document'),
                    ('create', 'file'), ('make', 'document'),
                    ('create', 'txt'), ('make', 'txt')],
    'api_key': [('connect', 'google'), ('connect', 'api'),
                ('add', 'key'), ('insert', 'key'), ('enter', 'key',
                ), ('api', 'key'), ('gemini', 'key'),
                ('remove', 'key'), ('delete', 'key'), ('forget', 'key'),
                ('disconnect', 'key'), ('key', 'from', 'file')],
    'note': [('take', 'note'), ('make', 'note'), ('new', 'note'),
             ('note',), ('write', 'down')],
    'help': [('help',), ('commands',), ('what', 'can', 'you', 'do'),
             ('list', 'commands'), ('skills',)],
    'time': [('time',), ('what', 'time'), ('current', 'time')],
    'date': [('date',), ('what', 'date'), ('what', 'day', 'is', 'it'),
             ('today',)],
    'joke': [('joke',), ('tell', 'joke'), ('make', 'me', 'laugh'),
             ('something', 'funny')],
    'system': [('specs',), ('specifications',), ('about', 'pc'),
               ('system', 'info'), ('about', 'computer'),
               ('how', 'much', 'ram'), ('ram',)],
    'who': [('who', 'are', 'you'), ('what', 'are', 'you'),
            ('your', 'name'), ('what', 'is', 'this')],
    'thanks': [('thanks',), ('thank', 'you'), ('thx',), ('appreciate', 'it')],
    'greeting': [('hello',), ('hi',), ('hey',), ('good', 'morning'),
                 ('good', 'afternoon'), ('good', 'evening'),
                 ('good', 'night'), ('howdy',), ('greetings',)],
    'clear': [('clear', 'chat'), ('clear', 'screen'),
              ('clear', 'history'), ('clear',)],
    'exit': [('bye',), ('quit',), ('exit',), ('close',), ('goodbye',),
             ('shut', 'down'), ('farewell',)],
}
for _it in INTENTS:
    _it['phrases'] = _it.get('phrases', []) + _INTENTS_EN_PHRASES.get(_it['name'], [])


def _match_phrase(words, phrase):
    """Нечёткий поиск фразы как подряд идущих слов. -> (score, индексы) | None"""
    n = len(phrase)
    best = None
    for i in range(len(words) - n + 1):
        sims = []
        ok = True
        for k in range(n):
            s = sim(words[i + k], phrase[k])
            if s < word_thr(words[i + k], phrase[k]):
                ok = False
                break
            sims.append(s)
        if ok:
            sc = sum(sims) / len(sims)
            if best is None or sc > best[0]:
                best = (sc, list(range(i, i + n)))
    return best


# предлоги: слово после них — не прямой объект команды
# (в «создай в папке работы презентацию» папка — это МЕСТО, а не цель команды)
_PREPOSITIONS = {'в', 'на', 'из', 'с', 'со', 'про', 'о', 'об', 'для', 'под',
                 'до', 'от', 'к', 'по', 'у', 'при'}


def _match_pair(words, verbs_s, nouns_s):
    """Глагол + существительное в любом месте (глагол раньше).

    Нужно для фраз вроде «создай в папке работы презентацию про ии».
    Существительное не берётся, если перед ним предлог: в «создай в папке
    работы презентацию» слову «папке» предшествует «в» — значит это указание
    места, а не объект команды."""
    verbs = verbs_s.split()
    nouns = nouns_s.split()
    best = None
    for vi in range(len(words)):
        sv = best_fuzzy(words[vi], verbs)
        if sv == 0:
            continue
        for ni in range(vi + 1, len(words)):
            if words[ni - 1] in _PREPOSITIONS and words[ni - 1] != words[vi]:
                continue
            sn = best_fuzzy(words[ni], nouns)
            if sn == 0:
                continue
            sc = (sv + sn) / 2
            if best is None or sc > best[0]:
                best = (sc, [vi, ni])
    return best


def match_intent(words):
    """Лучший интент для списка нормализованных слов.

    -> (score, длина_фразы, имя_интента, занятые_индексы) | None
    """
    cands = []
    for it in INTENTS:
        bonus = 0.2 if it.get('action') else 0.0
        for ph in it['phrases']:
            m = _match_phrase(words, ph)
            if m:
                cands.append((m[0] + bonus, len(ph), it['name'], m[1]))
        for verbs, nouns in it.get('pairs', []):
            m = _match_pair(words, verbs, nouns)
            if m:
                cands.append((m[0] + bonus, 2, it['name'], m[1]))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return cands[0]


def resolve_target(raw):
    """Пытается понять, что открыть: URL, сайт из базы или программу.

    -> (kind, key, score) | None, где kind in {'url','site','app'}"""
    if not raw:
        return None
    rl = raw.lower().replace('ё', 'е').strip()
    if re.match(r'^https?://', rl):
        return ('url', rl, 1.0)
    if re.match(r'^[\w-]+(\.[\w-]+)+(/\S*)?$', rl):
        return ('url', 'https://' + rl, 1.0)
    nw = normalize(raw).split()
    if not nw:
        return None
    best = None
    for table, kind in ((SITES, 'site'), (APPS, 'app')):
        for key in table:
            kw = key.split()
            if len(kw) > len(nw):
                continue
            for i in range(len(nw) - len(kw) + 1):
                sims = []
                ok = True
                for k in range(len(kw)):
                    s = sim(nw[i + k], kw[k])
                    if s < word_thr(nw[i + k], kw[k]):
                        ok = False
                        break
                    sims.append(s)
                if ok:
                    sc = sum(sims) / len(sims)
                    if best is None or sc > best[0]:
                        best = (sc, kind, key)
    if best:
        return (best[1], best[2], best[0])
    return None


# ----------------------------------------------------------------------------
# v5.1: поиск установленных программ (ярлыки «Пуска» + реестр App Paths)
# ----------------------------------------------------------------------------

def _start_menu_dirs():
    dirs = []
    for env in ('APPDATA', 'ProgramData'):
        base = os.environ.get(env)
        if base:
            d = os.path.join(base, 'Microsoft', 'Windows',
                             'Start Menu', 'Programs')
            if os.path.isdir(d):
                dirs.append(d)
    return dirs


def _app_paths_lookup(name):
    """Программа в реестре Windows (App Paths) -> путь к exe | None."""
    if os.name != 'nt':
        return None
    try:
        import winreg
    except Exception:
        return None
    clean = re.sub(r'[^\w ]', '', name).replace(' ', '')
    if not clean:
        return None
    for exe in (clean + '.exe', clean):
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                k = winreg.OpenKey(
                    hive,
                    r'Software\Microsoft\Windows\CurrentVersion\App Paths\\' + exe)
                val, _t = winreg.QueryValueEx(k, None)
                winreg.CloseKey(k)
                if val and os.path.isfile(val):
                    return val
            except Exception:
                continue
    return None


def _search_shortcut(name, strong_only=False):
    """Ищет программу по ярлыкам меню «Пуск» (нечётко, терпит опечатки).

    -> [(имя, путь, совпадение)] — лучшие первыми; пусто, если не нашли.
    strong_only — только точные/вложенные совпадения («роблокс» в
    «Roblox Player»), чтобы не перебивать известные сайты."""
    out, seen = [], set()
    target = normalize(name)
    if not target:
        return out
    exe = _app_paths_lookup(name)
    if exe:
        out.append((os.path.basename(exe), exe, 0.95))
    for base in _start_menu_dirs():
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith(('.lnk', '.url')):
                    continue
                stem = os.path.splitext(fn)[0]
                nstem = normalize(stem)
                if not nstem or stem in seen:
                    continue
                strong = (nstem == target or target in nstem
                          or nstem in target)
                if strong:
                    score = 1.0
                elif strong_only:
                    continue
                else:
                    score = best_fuzzy(target, nstem.split())
                    if score < 0.66:
                        continue
                seen.add(stem)
                out.append((stem, os.path.join(root, fn), score))
    out.sort(key=lambda h: -h[2])
    return out[:5]


# ----------------------------------------------------------------------------
def search_files(name, limit=6):
    """v7: поиск файлов для «найди файл X». -> [(путь, скор), ...].

    Ищем на рабочем столе, в документах, загрузках и домашней папке
    (глубина до 2 уровней), совпадение нечёткое — опечатки прощаются.
    Показываем свежие файлы первыми."""
    out = []
    target = normalize(name)
    if not target:
        return out
    home = os.path.expanduser('~')
    bases = [desktop_dir(), documents_dir(),
             os.path.join(home, 'Downloads'),
             os.path.join(home, 'Загрузки'), home]
    seen = set()
    exts = ('.txt', '.docx', '.pptx', '.xlsx', '.pdf', '.doc', '.ppt',
            '.xls', '.rtf', '.odt', '.csv', '.png', '.jpg', '.jpeg',
            '.mp3', '.mp4', '.zip', '.py', '.bat', '.lnk')
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        level1 = [base]
        try:
            level1 = level1 + [os.path.join(base, d)
                              for d in os.listdir(base)[:40]
                              if os.path.isdir(os.path.join(base, d))]
        except Exception:
            pass
        for root in level1:
            try:
                for fn in os.listdir(root):
                    if len(out) >= limit * 4:
                        break
                    if not fn.lower().endswith(exts):
                        continue
                    stem = normalize(os.path.splitext(fn)[0])
                    if not stem:
                        continue
                    p = os.path.join(root, fn)
                    if p in seen:
                        continue
                    seen.add(p)
                    if stem == target:
                        score = 1.0
                    elif target in stem or stem in target:
                        score = 0.9
                    else:
                        score = best_fuzzy(target, stem.split())
                        if score < 0.6:
                            continue
                    out.append((p, score))
            except Exception:
                continue
    # дедупликация по имени+размеру и сортировка: релевантность, потом свежесть
    uniq, seen2 = [], set()
    out.sort(key=lambda h: -h[1])
    for p, s in out:
        k = os.path.basename(p).lower()
        if k in seen2:
            continue
        seen2.add(k)
        uniq.append((p, s))
    try:
        uniq.sort(key=lambda h: (-h[1], -os.path.getmtime(h[0])))
    except Exception:
        pass
    return uniq[:limit]


# Системные пути (рабочий стол учитывает OneDrive-перенаправление)# ----------------------------------------------------------------------------

def desktop_dir():
    if os.name == 'nt':
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
            path, _ = winreg.QueryValueEx(key, 'Desktop')
            winreg.CloseKey(key)
            path = os.path.expandvars(path)
            if os.path.isdir(path):
                return path
        except Exception:
            pass
    # v7: если папки «Рабочий стол» нет (редкие Linux/macOS-сборки),
    # сохраняем в домашнюю папку, а не падаем с ошибкой записи
    d = os.path.join(os.path.expanduser('~'), 'Desktop')
    return d if os.path.isdir(d) else os.path.expanduser('~')


def documents_dir():
    d = os.path.join(os.path.expanduser('~'), 'Documents')
    return d if os.path.isdir(d) else os.path.expanduser('~')


def _fmt_gb(num):
    return ('%.1f' % num).replace('.', ',')


def _ram_total_gb():
    if os.name != 'nt':
        return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_uint64), ('ullAvailPhys', ctypes.c_uint64),
                ('ullTotalPageFile', ctypes.c_uint64), ('ullAvailPageFile', ctypes.c_uint64),
                ('ullTotalVirtual', ctypes.c_uint64), ('ullAvailVirtual', ctypes.c_uint64),
                ('ullAvailExtendedVirtual', ctypes.c_uint64)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / (1024.0 ** 3)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# MiniPPTX — генератор настоящих .pptx без библиотек (zip + OOXML)
# ----------------------------------------------------------------------------

_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')

_RELS_ROOT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" '
              'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
              'Target="ppt/presentation.xml"/></Relationships>')

_MASTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<p:sldMaster %s><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="0D0D1A"/>'
           '</a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree>'
           '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
           '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
           '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
           '</p:spTree></p:cSld>'
           '<p:clrMap bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" '
           'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
           'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
           '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
           '</p:sldLayoutIdLst></p:sldMaster>') % _NS

_MASTER_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
                'Target="../slideLayouts/slideLayout1.xml"/>'
                '<Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
                'Target="../theme/theme1.xml"/></Relationships>')

_LAYOUT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<p:sldLayout %s type="blank" preserve="1"><p:cSld name="Пустой макет">'
           '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
           '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
           '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
           '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
           '</p:sldLayout>') % _NS

_LAYOUT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
                'Target="../slideMasters/slideMaster1.xml"/></Relationships>')

_SLIDE_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" '
               'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
               'Target="../slideLayouts/slideLayout1.xml"/></Relationships>')

_THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'name="Neon Dark"><a:themeElements><a:clrScheme name="Neon Dark">'
          '<a:dk1><a:srgbClr val="0D0D1A"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
          '<a:dk2><a:srgbClr val="12122A"/></a:dk2><a:lt2><a:srgbClr val="E8E8F0"/></a:lt2>'
          '<a:accent1><a:srgbClr val="00F0FF"/></a:accent1>'
          '<a:accent2><a:srgbClr val="FF2EC8"/></a:accent2>'
          '<a:accent3><a:srgbClr val="7B2EFF"/></a:accent3>'
          '<a:accent4><a:srgbClr val="B6FF00"/></a:accent4>'
          '<a:accent5><a:srgbClr val="FF9E00"/></a:accent5>'
          '<a:accent6><a:srgbClr val="00FFA3"/></a:accent6>'
          '<a:hlink><a:srgbClr val="00F0FF"/></a:hlink>'
          '<a:folHlink><a:srgbClr val="7B2EFF"/></a:folHlink></a:clrScheme>'
          '<a:fontScheme name="Neon Dark">'
          '<a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
          '<a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
          '</a:fontScheme><a:fmtScheme name="Neon Dark">'
          '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
          '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
          '<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
          '<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
          '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
          '<a:effectStyle><a:effectLst/></a:effectStyle>'
          '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
          '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
          '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
          '</a:fmtScheme></a:themeElements></a:theme>')


class MiniPPTX(object):
    """Минимальный генератор презентаций PowerPoint (.pptx) на чистом Python.

    Собирает OOXML-пакет вручную и записывает zip-архив, который
    открывается в PowerPoint, LibreOffice и Google Slides."""
    W = 12192000   # ширина слайда, EMU (16:9)
    H = 6858000    # высота слайда, EMU

    def __init__(self):
        self.slides = []      # XML-строки фигур каждого слайда
        self.pics = []        # картинки слайда: (индекс_медиа, x, y, w, h)
        self.media = []       # [(имя_файла.png, байты)]
        self._media_keys = {}  # ключ -> индекс, чтобы не дублировать байты

    # ---------- элементы слайда ----------

    def add_slide(self):
        self.slides.append([])
        self.pics.append([])
        return len(self.slides) - 1

    def _shape(self, si, prst, x, y, w, h, fillxml, lnxml=''):
        shapes = self.slides[si]
        sid = len(shapes) + 2
        xml = ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Shape %d"/>'
               '<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
               '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
               '</a:xfrm><a:prstGeom prst="%s"><a:avLst/></a:prstGeom>%s%s</p:spPr>'
               '</p:sp>')
        shapes.append(xml % (sid, sid, x, y, w, h, prst, fillxml, lnxml))

    @staticmethod
    def _fillxml(fill, grad, alpha):
        if grad:
            return ('<a:gradFill><a:gsLst>'
                    '<a:gs pos="0"><a:srgbClr val="%s"/></a:gs>'
                    '<a:gs pos="100000"><a:srgbClr val="%s"/></a:gs>'
                    '</a:gsLst><a:lin ang="%d" scaled="1"/></a:gradFill>'
                    % (grad[0], grad[1], MiniPPTX._angle(grad)))
        if fill:
            a = ('<a:alpha val="%d"/>' % alpha) if alpha else ''
            return '<a:solidFill><a:srgbClr val="%s">%s</a:srgbClr></a:solidFill>' % (fill, a)
        return '<a:noFill/>'

    @staticmethod
    def _angle(grad):
        return grad[2] if len(grad) > 2 else 0

    def rect(self, si, x, y, w, h, fill=None, grad=None, alpha=None):
        self._shape(si, 'rect', x, y, w, h, self._fillxml(fill, grad, alpha))

    def ellipse(self, si, x, y, w, h, line, alpha=None, line_w=28575):
        a = ('<a:alpha val="%d"/>' % alpha) if alpha else ''
        ln = ('<a:ln w="%d"><a:solidFill><a:srgbClr val="%s">%s</a:srgbClr>'
              '</a:solidFill></a:ln>' % (line_w, line, a))
        self._shape(si, 'ellipse', x, y, w, h, '<a:noFill/>', ln)

    def card(self, si, x, y, w, h, fill='141B33', line='00F0FF', alpha=None,
             line_w=15875):
        """Неоновая подложка под картинку: тёмная панель + тонкая рамка."""
        a = ('<a:alpha val="%d"/>' % alpha) if alpha else ''
        fillxml = ('<a:solidFill><a:srgbClr val="%s">%s</a:srgbClr></a:solidFill>'
                   % (fill, a)) if fill else '<a:noFill/>'
        ln = ('<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln>'
              % (line_w, line)) if line else ''
        self._shape(si, 'roundRect', x, y, w, h, fillxml, ln)

    # ---------- картинки ----------

    def add_media(self, img, key=None):
        """Добавляет картинку (PNG или JPEG байты) в пакет и возвращает индекс.

        Формат определяется по магическим байтам: JPEG-фото из интернета
        и нарисованные PNG кладутся в один и тот же media-каталог."""
        if key is not None and key in self._media_keys:
            return self._media_keys[key]
        is_jpeg = img[:2] == b'\xff\xd8'
        ext = 'jpg' if is_jpeg else 'png'
        self.media.append(('image%d.%s' % (len(self.media) + 1, ext), img))
        idx = len(self.media) - 1
        if key is not None:
            self._media_keys[key] = idx
        return idx

    def picture(self, si, x, y, w, h, img, key=None, src_rect=None):
        """Вставляет картинку (PNG/JPEG) на слайд в прямоугольнике.

        src_rect=(l,t,r,b) — обрезка исходника в тысячных процентах
        (используется для центр-кропа фото под вертикальную карточку)."""
        idx = self.add_media(img, key)
        self.pics[si].append((idx, x, y, w, h, src_rect))

    def text(self, si, x, y, w, h, paras, anchor='t'):
        """paras — список абзацев:
        {'runs': [(текст, размер_сотые_пункта, жирный, цвет)],
         'align': 'l'|'ctr'|'r', 'spc': межстрочный_процент,
         'before': отступ_сверху_сотые_пункта}"""
        shapes = self.slides[si]
        sid = len(shapes) + 2
        pxml = []
        for pa in paras:
            algn = pa.get('align', 'l')
            spc = int(pa.get('spc', 140) * 1000)
            before = pa.get('before', 0)
            runs = []
            for (t, sz, b, color) in pa['runs']:
                runs.append(
                    '<a:r><a:rPr lang="ru-RU" sz="%d" b="%d" dirty="0">'
                    '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                    '<a:latin typeface="Segoe UI"/><a:cs typeface="Segoe UI"/>'
                    '</a:rPr><a:t>%s</a:t></a:r>' % (sz, 1 if b else 0, color, escape(t)))
            befxml = ('<a:spcBef><a:spcPts val="%d"/></a:spcBef>' % before) if before else ''
            pxml.append('<a:p><a:pPr algn="%s"><a:lnSpc><a:spcPct val="%d"/></a:lnSpc>'
                        '%s</a:pPr>%s</a:p>' % (algn, spc, befxml, ''.join(runs)))
        xml = ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Text %d"/>'
               '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
               '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
               '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
               '<a:noFill/></p:spPr><p:txBody>'
               '<a:bodyPr wrap="square" rtlCol="0" anchor="%s"/><a:lstStyle/>'
               '%s</p:txBody></p:sp>')
        shapes.append(xml % (sid, sid, x, y, w, h, anchor, ''.join(pxml)))

    # ---------- сборка файла ----------

    def _slide_xml(self, si):
        shapes = self.slides[si]
        pics = self.pics[si]
        base = len(shapes) + 2   # id фигур 2..N, картинки получают N+1..
        picxml = []
        for j, pic in enumerate(pics):
            idx, x, y, w, h = pic[:5]
            sr = pic[5] if len(pic) > 5 else None
            srcxml = ('<a:srcRect l="%d" t="%d" r="%d" b="%d"/>' % sr
                      if sr else '')
            picxml.append(
                '<p:pic><p:nvPicPr><p:cNvPr id="%d" name="%s"/>'
                '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
                '<p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId%d"/>%s'
                '<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                '</p:spPr></p:pic>'
                % (base + j, self.media[idx][0], j + 2, srcxml, x, y, w, h))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sld %s><p:cSld><p:bg><p:bgPr><a:solidFill>'
                '<a:srgbClr val="0D0D1A"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
                '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
                '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
                '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>%s%s'
                '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
                '</p:sld>') % (_NS, ''.join(shapes), ''.join(picxml))

    def _presentation_xml(self):
        n = len(self.slides)
        sld_ids = ''.join('<p:sldId id="%d" r:id="rId%d"/>' % (255 + i, i + 1)
                          for i in range(1, n + 1))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:presentation %s><p:sldMasterIdLst>'
                '<p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                '<p:sldIdLst>%s</p:sldIdLst><p:sldSz cx="%d" cy="%d"/>'
                '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
                % (_NS, sld_ids, self.W, self.H))

    def _presentation_rels(self):
        n = len(self.slides)
        parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
                 'Target="slideMasters/slideMaster1.xml"/>']
        for i in range(1, n + 1):
            parts.append('<Relationship Id="rId%d" '
                         'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
                         'Target="slides/slide%d.xml"/>' % (i + 1, i))
        parts.append('<Relationship Id="rId%d" '
                     'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
                     'Target="theme/theme1.xml"/>' % (n + 2))
        parts.append('</Relationships>')
        return ''.join(parts)

    def _slide_rels(self, si):
        """Связи конкретного слайда: макет (rId1) + картинки (rId2..)."""
        parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
                 'Target="../slideLayouts/slideLayout1.xml"/>']
        for j, pic in enumerate(self.pics[si]):
            parts.append('<Relationship Id="rId%d" '
                         'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                         'Target="../media/%s"/>' % (j + 2, self.media[pic[0]][0]))
        parts.append('</Relationships>')
        return ''.join(parts)

    def save(self, path):
        n = len(self.slides)
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" '
              'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Default Extension="png" ContentType="image/png"/>'
              '<Default Extension="jpg" ContentType="image/jpeg"/>'
              '<Override PartName="/ppt/presentation.xml" ContentType='
              '"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
              '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType='
              '"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
              '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType='
              '"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>']
        for i in range(1, n + 1):
            ct.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType='
                      '"application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % i)
        ct.append('<Override PartName="/ppt/theme/theme1.xml" ContentType='
                  '"application/vnd.openxmlformats-officedocument.theme+xml"/>')
        ct.append('</Types>')

        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', ''.join(ct))
            z.writestr('_rels/.rels', _RELS_ROOT)
            z.writestr('ppt/presentation.xml', self._presentation_xml())
            z.writestr('ppt/_rels/presentation.xml.rels', self._presentation_rels())
            z.writestr('ppt/theme/theme1.xml', _THEME)
            z.writestr('ppt/slideMasters/slideMaster1.xml', _MASTER)
            z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels', _MASTER_RELS)
            z.writestr('ppt/slideLayouts/slideLayout1.xml', _LAYOUT)
            z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', _LAYOUT_RELS)
            for i, shapes in enumerate(self.slides, 1):
                z.writestr('ppt/slides/slide%d.xml' % i, self._slide_xml(i - 1))
                z.writestr('ppt/slides/_rels/slide%d.xml.rels' % i,
                           self._slide_rels(i - 1))
            for name, img in self.media:
                z.writestr('ppt/media/' + name, img)


# ----------------------------------------------------------------------------
# MiniDOCX — генератор настоящих .docx без библиотек (zip + OOXML)
# ----------------------------------------------------------------------------

class MiniDOCX(object):
    """Минимальный генератор документов Word на чистом Python.

    Собирает OOXML-пакет вручную и записывает zip-архив, который
    открывается в Word, LibreOffice и Google Docs."""

    def __init__(self):
        self.paras = []

    def para(self, text, sz=22, bold=False, italic=False, color='22223A',
             align='left', before=0, after=120, bullet=False):
        """Абзац. sz — размер в половинах пункта (22 = 11 пт)."""
        self.paras.append({'text': str(text), 'sz': sz, 'bold': bold,
                           'italic': italic, 'color': color, 'align': align,
                           'before': before, 'after': after, 'bullet': bullet})

    def bullet(self, text, mark='•'):
        self.para('%s  %s' % (mark, text), sz=22, color='33334A', after=80,
                  bullet=True)

    def _p(self, p):
        j = {'left': 'left', 'center': 'center', 'right': 'right'}.get(
            p['align'], 'left')
        rpr = ('<w:rPr><w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI"/>'
               + ('<w:b/>' if p['bold'] else '')
               + ('<w:i/>' if p['italic'] else '')
               + '<w:color w:val="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/>'
                 '</w:rPr>' % (p['color'], p['sz'], p['sz']))
        ind = '<w:ind w:left="567"/>' if p['bullet'] else ''
        return ('<w:p><w:pPr><w:spacing w:before="%d" w:after="%d" '
                'w:line="276" w:lineRule="auto"/><w:jc w:val="%s"/>%s</w:pPr>'
                '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                % (p['before'], p['after'], j, ind, rpr, escape(p['text'])))

    def save(self, path):
        body = ''.join(self._p(p) for p in self.paras)
        document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    'wordprocessingml/2006/main"><w:body>%s'
                    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
                    'w:left="1134" w:header="709" w:footer="709" '
                    'w:gutter="0"/></w:sectPr></w:body></w:document>' % body)
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="'
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '</Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/></Relationships>')
        drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', ct)
            z.writestr('_rels/.rels', rels)
            z.writestr('word/document.xml', document)
            z.writestr('word/_rels/document.xml.rels', drels)


# ----------------------------------------------------------------------------
# Рисование PNG-картинок на чистом Python (stdlib) — иллюстрации для слайдов
# ----------------------------------------------------------------------------


class PNGCanvas(object):
    """Растровый холст: фигуры рисуются пикселями, сохранение — настоящий PNG."""

    def __init__(self, w, h, bg=(16, 12, 30)):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        for i in range(0, len(self.px), 3):
            self.px[i], self.px[i + 1], self.px[i + 2] = bg

    def set(self, x, y, c, a=255):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if a >= 255:
                self.px[i], self.px[i + 1], self.px[i + 2] = c
            elif a > 0:
                k = a / 255.0
                self.px[i] = int(c[0] * k + self.px[i] * (1 - k))
                self.px[i + 1] = int(c[1] * k + self.px[i + 1] * (1 - k))
                self.px[i + 2] = int(c[2] * k + self.px[i + 2] * (1 - k))

    def line(self, x0, y0, x1, y1, c, a=255, t=1):
        """Отрезок (Брезенхэм); t — толщина."""
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        r = t / 2.0
        ir = int(r)
        while True:
            if t <= 1:
                self.set(x0, y0, c, a)
            else:
                for oy in range(-ir, ir + 1):
                    for ox in range(-ir, ir + 1):
                        if ox * ox + oy * oy <= r * r:
                            self.set(x0 + ox, y0 + oy, c, a)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def rect(self, x, y, w, h, c, a=255):
        for yy in range(int(y), int(y + h)):
            for xx in range(int(x), int(x + w)):
                self.set(xx, yy, c, a)

    def frame(self, x, y, w, h, c, t=3, a=255):
        x, y, w, h = int(x), int(y), int(w), int(h)
        self.line(x, y, x + w, y, c, a, t)
        self.line(x, y + h, x + w, y + h, c, a, t)
        self.line(x, y, x, y + h, c, a, t)
        self.line(x + w, y, x + w, y + h, c, a, t)

    def circle(self, cx, cy, r, c, a=255, fill=True, t=2):
        cx, cy = int(cx), int(cy)
        if fill:
            r = int(r)
            for yy in range(cy - r, cy + r + 1):
                for xx in range(cx - r, cx + r + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                        self.set(xx, yy, c, a)
        else:
            n = max(24, int(8 * r))
            for i in range(n):
                ang = 2 * math.pi * i / n
                self.circle(cx + r * math.cos(ang), cy + r * math.sin(ang),
                            max(1, t // 2), c, a)

    def glow(self, cx, cy, r, c, a=120):
        """Мягкое неоновое свечение: ярче к центру."""
        for yy in range(int(cy - r), int(cy + r) + 1):
            for xx in range(int(cx - r), int(cx + r) + 1):
                d = math.hypot(xx - cx, yy - cy)
                if d <= r:
                    k = max(0.0, 1.0 - d / r)
                    self.set(xx, yy, c, int(a * k * k))

    def poly(self, pts, c, a=255):
        """Заливка многоугольника (сканирующие линии)."""
        ys = [p[1] for p in pts]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            for i in range(len(pts)):
                xA, yA = pts[i]
                xB, yB = pts[(i + 1) % len(pts)]
                if (yA <= y < yB) or (yB <= y < yA):
                    xs.append(xA + (y - yA) * (xB - xA) / float(yB - yA))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(int(xs[i]), int(xs[i + 1]) + 1):
                    self.set(x, y, c, a)

    def stars(self, n, seed=1, c=(200, 210, 255)):
        rnd = random.Random(seed)
        for _ in range(n):
            self.set(rnd.randrange(self.w), rnd.randrange(self.h),
                     c, rnd.randrange(90, 220))

    def png(self):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]

        def chunk(tag, data):
            out = struct.pack('>I', len(data)) + tag + data
            return out + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

        ihdr = struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
                chunk(b'IDAT', zlib.compress(bytes(raw), 6)) +
                chunk(b'IEND', b''))


_NEON = {'cyan': (0, 240, 255), 'pink': (255, 46, 200), 'violet': (123, 46, 255),
         'lime': (182, 255, 0), 'amber': (255, 158, 0), 'mint': (0, 255, 163),
         'white': (232, 232, 240), 'dim': (140, 150, 190)}


def _art_neural(c):
    cyan, pink, violet = _NEON['cyan'], _NEON['pink'], _NEON['violet']
    c.stars(36, seed=7)
    layers = [(70, [150, 230, 310]), (210, [110, 190, 270, 350]), (350, [160, 230, 300])]
    cols = [cyan, pink, violet]
    for li in range(len(layers) - 1):
        x0, ys0 = layers[li]
        x1, ys1 = layers[li + 1]
        for y0 in ys0:
            for y1 in ys1:
                c.line(x0 + 12, y0, x1 - 12, y1, cols[li % 3], a=45)
    for li, (x, ys) in enumerate(layers):
        col = cols[li % 3]
        for y in ys:
            c.glow(x, y, 26, col, 90)
            c.circle(x, y, 11, col)
            c.circle(x, y, 4, (255, 255, 255))


def _art_rocket(c):
    cyan, pink, amber = _NEON['cyan'], _NEON['pink'], _NEON['amber']
    c.stars(60, seed=3)
    c.glow(210, 480, 150, _NEON['violet'], 70)
    c.circle(210, 485, 120, (60, 40, 110))
    c.circle(210, 485, 120, _NEON['violet'], a=50)
    c.poly([(190, 90), (230, 90), (236, 240), (184, 240)], _NEON['white'])
    c.poly([(190, 90), (210, 40), (230, 90)], cyan)
    c.circle(210, 140, 17, (13, 13, 26))
    c.circle(210, 140, 13, cyan)
    c.poly([(184, 190), (150, 260), (184, 250)], pink)
    c.poly([(236, 190), (270, 260), (236, 250)], pink)
    c.poly([(188, 245), (232, 245), (210, 340)], amber)
    c.poly([(197, 245), (223, 245), (210, 300)], (255, 230, 0))
    c.circle(90, 120, 6, cyan)
    c.line(70, 100, 82, 112, _NEON['white'], a=140)
    c.line(98, 128, 110, 140, _NEON['white'], a=140)


def _art_planets(c):
    c.stars(60, seed=11)

    def ring(a0, a1):
        n = 220
        for i in range(n):
            ang = a0 + (a1 - a0) * i / (n - 1)
            c.circle(180 + 150 * math.cos(ang), 240 + 42 * math.sin(ang),
                     3, _NEON['pink'], a=190)

    ring(math.pi, 2 * math.pi)
    c.glow(180, 240, 130, _NEON['cyan'], 60)
    c.circle(180, 240, 95, (24, 60, 90))
    for (yy, k) in ((205, .9), (240, 1.0), (275, .9)):
        rx = int(95 * math.sqrt(max(0.0, 1 - ((yy - 240) / 95.0) ** 2)) * k)
        c.line(180 - rx, yy, 180 + rx, yy, _NEON['cyan'], a=130, t=3)
    ring(0, math.pi)
    c.glow(340, 110, 44, _NEON['amber'], 80)
    c.circle(340, 110, 22, (110, 85, 50))
    c.circle(332, 104, 5, (80, 60, 35))
    c.circle(350, 118, 4, (80, 60, 35))


def _art_sprout(c):
    amber, lime = _NEON['amber'], (46, 204, 113)
    c.glow(350, 90, 70, amber, 110)
    c.circle(350, 90, 26, amber)
    for i in range(12):
        ang = i * math.pi / 6
        c.line(350 + 34 * math.cos(ang), 90 + 34 * math.sin(ang),
               350 + 48 * math.cos(ang), 90 + 48 * math.sin(ang), amber, a=180, t=2)
    c.rect(60, 350, 300, 44, (70, 50, 35))
    rnd = random.Random(4)
    for _ in range(50):
        x = rnd.randrange(64, 352)
        c.line(x, 350, x + 3, 358 + rnd.randrange(6), (50, 35, 25), a=140)
    for i in range(90):
        y = 350 - i * 1.6
        x = 210 + 14 * math.sin(i / 12.0)
        c.line(x, y, x, y + 2, (40, 180, 90), t=3)
    c.poly([(206, 250), (140, 200), (128, 260), (196, 282)], lime)
    c.poly([(216, 230), (290, 180), (296, 244), (222, 264)], lime)
    c.line(206, 250, 140, 215, (30, 140, 80), a=170)
    c.line(216, 236, 288, 190, (30, 140, 80), a=170)


def _art_robot(c):
    cyan, pink = _NEON['cyan'], _NEON['pink']
    c.line(210, 100, 210, 60, cyan, t=3)
    c.glow(210, 52, 18, pink, 120)
    c.circle(210, 52, 8, pink)
    c.rect(150, 100, 120, 96, (30, 38, 66))
    c.frame(150, 100, 120, 96, cyan, t=3)
    c.glow(185, 140, 16, cyan, 110)
    c.glow(235, 140, 16, pink, 110)
    c.circle(185, 140, 10, cyan)
    c.circle(235, 140, 10, pink)
    for i in range(5):
        c.line(180 + i * 15, 172, 180 + i * 15, 178, _NEON['dim'], t=2)
    c.rect(138, 128, 12, 34, cyan)
    c.rect(270, 128, 12, 34, cyan)
    c.rect(160, 210, 100, 120, (30, 38, 66))
    c.frame(160, 210, 100, 120, cyan, t=3)
    c.circle(185, 250, 8, pink)
    c.circle(215, 250, 8, cyan)
    c.circle(235, 250, 8, _NEON['lime'])
    c.rect(180, 278, 60, 32, (10, 14, 28))
    for i in range(4):
        c.rect(186 + i * 14, 284, 8, 18, _NEON['lime'], a=200)
    c.line(160, 225, 118, 268, cyan, t=5)
    c.line(260, 225, 302, 268, cyan, t=5)
    c.circle(118, 272, 9, pink)
    c.circle(302, 272, 9, pink)
    c.rect(175, 330, 18, 48, cyan)
    c.rect(227, 330, 18, 48, cyan)
    c.rect(165, 378, 38, 14, pink)
    c.rect(217, 378, 38, 14, pink)


def _art_globe(c):
    cyan, lime = _NEON['cyan'], _NEON['lime']
    cx, cy, r = 210, 230, 130
    c.glow(cx, cy, r + 40, cyan, 60)
    c.circle(cx, cy, r, (16, 40, 60))
    for (yy, k) in ((cy - 70, .95), (cy, 1.0), (cy + 70, .95)):
        rx = int(r * math.sqrt(max(0.0, 1 - ((yy - cy) / float(r)) ** 2)) * k)
        c.line(cx - rx, yy, cx + rx, yy, cyan, a=150, t=2)
    for rx in (int(r * .35), int(r * .75)):
        n = 90
        for i in range(n):
            ang = -math.pi / 2 + math.pi * i / (n - 1)
            c.circle(cx + rx * math.cos(ang), cy + r * math.sin(ang), 2, cyan, a=150)
    c.circle(cx, cy, r, cyan, fill=False, t=3)
    pts = [(150, 180), (250, 210), (190, 300), (280, 270), (135, 260)]
    for (x, y) in pts:
        c.glow(x, y, 12, lime, 120)
        c.circle(x, y, 5, lime)
    for i in range(len(pts) - 1):
        c.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], lime, a=90)


def _art_lock(c):
    cyan, lime = _NEON['cyan'], _NEON['lime']
    pts = [(210, 50), (320, 95), (320, 220), (210, 300), (100, 220), (100, 95)]
    c.poly(pts, (26, 34, 64))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        c.line(a[0], a[1], b[0], b[1], cyan, t=3)
    c.glow(210, 200, 90, cyan, 50)
    n = 60
    for i in range(n):
        ang = math.pi + math.pi * i / (n - 1)
        c.circle(210 + 42 * math.cos(ang), 168 + 42 * math.sin(ang), 4, lime)
    c.rect(160, 168, 100, 78, (26, 34, 64))
    c.frame(160, 168, 100, 78, lime, t=3)
    c.circle(210, 196, 9, lime)
    c.rect(206, 198, 8, 24, lime)


def _art_pulse(c):
    pink, lime = _NEON['pink'], _NEON['lime']
    c.glow(210, 180, 110, pink, 80)
    c.circle(172, 150, 46, pink)
    c.circle(248, 150, 46, pink)
    c.poly([(130, 168), (290, 168), (210, 290)], pink)
    c.poly([(152, 168), (268, 168), (210, 260)], (255, 130, 220))
    y = 380
    ecg = [(40, y), (140, y), (165, y - 30), (190, y + 55), (215, y - 70),
           (240, y), (380, y)]
    for i in range(len(ecg) - 1):
        c.line(ecg[i][0], ecg[i][1], ecg[i + 1][0], ecg[i + 1][1], lime, t=3)
    for i in range(1, len(ecg) - 1):
        c.glow(ecg[i][0], ecg[i][1], 10, lime, 120)


def _art_code(c):
    cyan, pink, lime, violet = (_NEON['cyan'], _NEON['pink'], _NEON['lime'],
                                _NEON['violet'])
    c.rect(50, 70, 320, 330, (24, 30, 56))
    c.frame(50, 70, 320, 330, _NEON['dim'], t=2)
    c.rect(50, 70, 320, 36, (34, 42, 76))
    for i, col in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        c.circle(78 + i * 26, 88, 8, col)
    rnd = random.Random(5)
    y = 130
    while y < 384:
        x = 74 + rnd.randrange(0, 3) * 18
        for _ in range(rnd.randrange(2, 5)):
            w = rnd.randrange(18, 76)
            col = (cyan, pink, lime, violet, _NEON['dim'])[rnd.randrange(5)]
            c.rect(x, y, w, 12, col, a=200)
            x += w + 14
            if x > 348:
                break
        y += 32
    c.rect(74, 366, 14, 12, lime)


def _art_chart(c):
    cyan, violet, pink, amber, lime = (_NEON['cyan'], _NEON['violet'],
                                       _NEON['pink'], _NEON['amber'], _NEON['lime'])
    c.line(70, 60, 70, 380, _NEON['dim'], t=3)
    c.line(70, 380, 385, 380, _NEON['dim'], t=3)
    for (x, h, col) in ((100, 70, cyan), (152, 120, violet), (204, 175, pink),
                        (256, 235, amber), (308, 295, lime)):
        c.rect(x, 380 - h, 36, h, col, a=190)
        c.rect(x, 380 - h, 36, 8, col)
    pts = [(118, 380 - 82), (170, 380 - 132), (222, 380 - 190),
           (274, 380 - 250), (326, 380 - 312)]
    for i in range(len(pts) - 1):
        c.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
               (255, 255, 255), t=3)
    c.line(302, 62, 332, 40, (255, 255, 255), t=3)
    c.line(306, 44, 332, 40, (255, 255, 255), t=3)
    c.line(328, 66, 332, 40, (255, 255, 255), t=3)


def _art_book(c):
    cyan, pink = _NEON['cyan'], _NEON['pink']
    c.glow(210, 240, 150, _NEON['violet'], 55)
    c.poly([(210, 130), (80, 100), (80, 330), (210, 360)], (30, 40, 70))
    c.poly([(210, 130), (340, 100), (340, 330), (210, 360)], (36, 48, 82))
    c.line(210, 130, 210, 360, (255, 255, 255), t=3)
    for i in range(6):
        y = 170 + i * 30
        c.line(100, y + (i % 2) * 6, 190, y + 10 + (i % 2) * 6, cyan, a=120)
        c.line(230, y + (i % 2) * 6, 320, y + 10 + (i % 2) * 6, pink, a=120)


def _art_gear(c):
    cyan, pink = _NEON['cyan'], _NEON['pink']

    def gear(cx, cy, r, col):
        c.glow(cx, cy, r + 30, col, 55)
        c.circle(cx, cy, r, (30, 38, 66))
        c.circle(cx, cy, r, col, fill=False, t=4)
        for i in range(12):
            ang = i * math.pi / 6
            c.line(cx + (r - 4) * math.cos(ang), cy + (r - 4) * math.sin(ang),
                   cx + (r + 16) * math.cos(ang), cy + (r + 16) * math.sin(ang),
                   col, t=6)
        c.circle(cx, cy, r // 3, col, fill=False, t=4)

    gear(160, 200, 80, cyan)
    gear(300, 300, 55, pink)


def _art_dna(c):
    cyan, pink = _NEON['cyan'], _NEON['pink']
    c.stars(30, seed=17)
    for i in range(310):
        y = 55 + i * 1.15
        if y > 415:
            break
        t_ = i * 0.035
        x1 = 210 + 90 * math.sin(t_)
        x2 = 210 + 90 * math.sin(t_ + math.pi)
        c.circle(x1, y, 4, cyan)
        c.circle(x2, y, 4, pink)
        if i % 14 == 0:
            c.line(x1, y, x2, y, _NEON['dim'], a=110, t=2)


def _art_galaxy(c):
    c.stars(50, seed=13)
    for arm in range(2):
        col = (_NEON['cyan'], _NEON['pink'])[arm]
        for i in range(150):
            t_ = i / 150.0
            ang = arm * math.pi + t_ * 4.4
            r = 18 + t_ * 150
            c.circle(210 + r * math.cos(ang) * 0.95,
                     230 + r * math.sin(ang) * 0.55,
                     3 if t_ < .6 else 2, col, a=200)
    c.glow(210, 230, 46, _NEON['amber'], 120)
    c.circle(210, 230, 14, (255, 240, 200))


_ART_PAINTERS = {'neural': _art_neural, 'rocket': _art_rocket, 'planets': _art_planets,
                 'sprout': _art_sprout, 'robot': _art_robot, 'globe': _art_globe,
                 'lock': _art_lock, 'pulse': _art_pulse, 'code': _art_code,
                 'chart': _art_chart, 'book': _art_book, 'gear': _art_gear,
                 'dna': _art_dna, 'galaxy': _art_galaxy}
_ART_CACHE = {}


def art_png(name):
    """PNG-байты (420x460) с тематической неоновой картинкой."""
    name = name if name in _ART_PAINTERS else 'chart'
    if name not in _ART_CACHE:
        cnv = PNGCanvas(420, 460)
        _ART_PAINTERS[name](cnv)
        _ART_CACHE[name] = cnv.png()
    return _ART_CACHE[name]


# ----------------------------------------------------------------------------
# MiniXLSX — генератор настоящих .xlsx без библиотек (v7)
# ----------------------------------------------------------------------------

_XLSX_COLS = 0x7FFF      # максимум колонок на листе
_COL_NAME_CACHE = {}


def _col_name(idx):
    """0 -> A, 25 -> Z, 26 -> AA (для адресов ячеек)."""
    if idx in _COL_NAME_CACHE:
        return _COL_NAME_CACHE[idx]
    n, s = idx, ''
    while True:
        s = chr(65 + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            break
    _COL_NAME_CACHE[idx] = s
    return s


class MiniXLSX(object):
    """Минимальный генератор таблиц Excel на чистом Python.

    Собирает SpreadsheetML-пакет вручную (zip + XML): стили, шапка
    с заливкой, закрепление первой строки, автофильтр. Открывается
    в Excel, LibreOffice Calc и Google Sheets."""

    def __init__(self, sheet_title='Лист1'):
        self.sheet_title = str(sheet_title)[:31] or 'Лист1'
        self.rows = []          # [[(значение, тип), ...], ...]
        self.widths = {}        # индекс_колонки -> ширина (символы)

    def set_width(self, col, width):
        self.widths[int(col)] = min(max(int(width), 6), 80)

    def add_row(self, values, header=False):
        """values — список строк/чисел. header=True — строка-шапка."""
        out = []
        for v in values:
            if header or isinstance(v, str) and not self._is_number(v):
                out.append((str(v) if v is not None else '', 's'))
            else:
                out.append((v, 'n'))
        self.rows.append((out, bool(header)))

    @staticmethod
    def _is_number(v):
        try:
            float(str(v).replace(',', '.'))
            return True
        except Exception:
            return False

    @staticmethod
    def _cell_xml(v, t, style, ref):
        if t == 'n':
            txt = ('%.10f' % float(v)).rstrip('0').rstrip('.')
            return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, txt)
        # строки экранируем: пробелы и спецсимволы
        return ('<c r="%s" t="inlineStr" s="%d"><is><t xml:space="preserve">'
                '%s</t></is></c>' % (ref, style, escape(str(v))))

    def _sheet_xml(self):
        total = max((len(r) for r, _ in self.rows), default=1)
        height = sum(1 for _ in self.rows) or 1
        # ширины: авто по содержимому, если явно не задано
        cols = []
        for ci in range(total):
            w = self.widths.get(ci)
            if w is None:
                longest = 8
                for r, _hdr in self.rows:
                    if ci < len(r):
                        cell = str(r[ci][0])
                        longest = max(longest, min(len(cell) + 2, 60))
                w = longest
            cols.append('<col min="%d" max="%d" width="%d" customWidth="1"/>'
                        % (ci + 1, ci + 1, w))
        rows = []
        for ri, (r, hdr) in enumerate(self.rows, 1):
            cells = []
            for ci, (v, t) in enumerate(r):
                style = 2 if hdr else 1
                if t == 'n' and not hdr:
                    style = 3   # числа с разрядкой тысяч
                ref = '%s%d' % (_col_name(ci), ri)
                cells.append(self._cell_xml(v, t, style, ref))
            rows.append('<row r="%d">%s</row>'
                        % (ri, ''.join(cells)))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main">'
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
                'state="frozen"/></sheetView></sheetViews>'
                '<cols>%s</cols><sheetData>%s</sheetData>'
                '<autoFilter ref="A1:%s%d"/>'
                '</worksheet>'
                % (''.join(cols), ''.join(rows), _col_name(total - 1), height))

    def save(self, path):
        styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<styleSheet xmlns="http://schemas.openxmlformats.org/'
                  'spreadsheetml/2006/main">'
                  '<numFmts count="1"><numFmt numFmtId="164" '
                  'formatCode="#,##0.##"/></numFmts>'
                  '<fonts count="3">'
                  '<font><sz val="11"/><name val="Calibri"/></font>'
                  '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/>'
                  '<name val="Calibri"/></font>'
                  '<font><sz val="11"/><color rgb="FF8A90A5"/>'
                  '<name val="Calibri"/></font></fonts>'
                  '<fills count="4">'
                  '<fill><patternFill patternType="none"/></fill>'
                  '<fill><patternFill patternType="gray125"/></fill>'
                  '<fill><patternFill patternType="solid">'
                  '<fgColor rgb="FF3A2E8C"/><bgColor indexed="64"/>'
                  '</patternFill></fill>'
                  '<fill><patternFill patternType="solid">'
                  '<fgColor rgb="FFF0F0FA"/><bgColor indexed="64"/>'
                  '</patternFill></fill></fills>'
                  '<borders count="2">'
                  '<border><left/><right/><top/><bottom/><diagonal/></border>'
                  '<border><left style="thin"><color rgb="FFD9D9E8"/></left>'
                  '<right style="thin"><color rgb="FFD9D9E8"/></right>'
                  '<top style="thin"><color rgb="FFD9D9E8"/></top>'
                  '<bottom style="thin"><color rgb="FFD9D9E8"/></bottom>'
                  '<diagonal/></border></borders>'
                  '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" '
                  'fillId="0" borderId="0"/></cellStyleXfs>'
                  '<cellXfs count="4">'
                  # 1: обычная ячейка (перенос и рамки)
                  '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" '
                  'xfId="0" applyAlignment="1">'
                  '<alignment vertical="center" wrapText="1"/></xf>'
                  # 2: шапка (белый жирный на фиолетовом, рамки)
                  '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" '
                  'xfId="0" applyAlignment="1" applyFill="1">'
                  '<alignment vertical="center" wrapText="1"/></xf>'
                  # 3: число с разрядкой
                  '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" '
                  'xfId="0" applyNumberFormat="1" applyAlignment="1">'
                  '<alignment vertical="center"/></xf>'
                  '</cellXfs>'
                  '<cellStyles count="1"><cellStyle name="Normal" '
                  'xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<workbook xmlns="http://schemas.openxmlformats.org/'
                    'spreadsheetml/2006/main" xmlns:r="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships">'
                    '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>'
                    '</workbook>' % escape(self.sheet_title))
        workbook_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                         '<Relationships xmlns="http://schemas.openxmlformats.'
                         'org/package/2006/relationships">'
                         '<Relationship Id="rId1" Type="http://schemas.'
                         'openxmlformats.org/officeDocument/2006/'
                         'relationships/worksheet" Target="worksheets/'
                         'sheet1.xml"/>'
                         '<Relationship Id="rId2" Type="http://schemas.'
                         'openxmlformats.org/officeDocument/2006/'
                         'relationships/styles" Target="styles.xml"/>'
                         '</Relationships>')
        root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.'
                     'openxmlformats.org/officeDocument/2006/'
                     'relationships/officeDocument" '
                     'Target="xl/workbook.xml"/></Relationships>')
        content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                         '<Types xmlns="http://schemas.openxmlformats.org/'
                         'package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/'
                         'vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/'
                         'xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType='
                         '"application/vnd.openxmlformats-officedocument.'
                         'spreadsheetml.sheet.main+xml"/>'
                         '<Override PartName="/xl/worksheets/sheet1.xml" '
                         'ContentType="application/vnd.openxmlformats-'
                         'officedocument.spreadsheetml.worksheet+xml"/>'
                         '<Override PartName="/xl/styles.xml" ContentType='
                         '"application/vnd.openxmlformats-officedocument.'
                         'spreadsheetml.styles+xml"/></Types>')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', content_types)
            z.writestr('_rels/.rels', root_rels)
            z.writestr('xl/workbook.xml', workbook)
            z.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
            z.writestr('xl/worksheets/sheet1.xml', self._sheet_xml())
            z.writestr('xl/styles.xml', styles)


def xlsx_content_for(topic):
    """Содержимое таблицы по теме: строки-факты + шапка. -> (шапка, строки)."""
    topic = topic.strip().strip(' «»"\'')
    content = content_for(topic, 6)
    secs = content['sections'][:6]
    header = ['Раздел', 'Ключевой тезис', 'Ещё факт', 'Источник текста']
    rows = []
    for sec in secs:
        title, bullets = sec[0], sec[1]
        b1 = bullets[0] if bullets else ''
        b2 = bullets[1] if len(bullets) > 1 else ''
        rows.append([title, str(b1), str(b2), content['source']])
    return header, rows


ACCENTS = ['00F0FF', 'FF2EC8', '7B2EFF', 'B6FF00', 'FF9E00', '00FFA3']


# ----------------------------------------------------------------------------
# v5.0. ГЕНЕРАТИВНЫЙ АРТ-ДВИЖОК: мотив + палитра вместо готовых картинок.
# Идея: фиксированный набор иллюстраций не может покрыть любую тему
# («песок», «кораллы», «футбол»...). Поэтому картинка СИНТЕЗИРУЕТСЯ под тему:
#   1) Gemini сам выбирает мотив и палитру по смыслу раздела (знает любую тему);
#   2) без Gemini — семантическая таблица ~400 корней слов -> (мотив, палитра);
#   3) совсем невиданная тема — уникальный узор из хэша темы (никаких
#      случайных «мозгов» для песка).
# ----------------------------------------------------------------------------

ART_PALETTES = {
    'sand':    ((38, 28, 14), (222, 185, 110), (150, 108, 52), (255, 224, 160)),
    'ocean':   ((8, 20, 38), (56, 150, 235), (20, 80, 150), (150, 225, 255)),
    'forest':  ((10, 24, 14), (70, 190, 110), (30, 110, 60), (190, 255, 180)),
    'fire':    ((30, 10, 6), (255, 120, 40), (180, 40, 20), (255, 220, 120)),
    'ice':     ((16, 26, 40), (170, 220, 255), (90, 150, 210), (240, 250, 255)),
    'sunset':  ((30, 14, 30), (255, 120, 160), (255, 170, 70), (255, 230, 180)),
    'dawn':    ((26, 20, 34), (255, 180, 140), (190, 120, 160), (255, 240, 200)),
    'storm':   ((16, 18, 26), (140, 160, 200), (70, 84, 120), (220, 230, 255)),
    'cyber':   ((10, 12, 24), (0, 240, 255), (255, 46, 200), (180, 140, 255)),
    'mono':    ((18, 18, 20), (220, 220, 225), (140, 140, 150), (255, 255, 255)),
    'gold':    ((28, 22, 8), (255, 200, 60), (170, 130, 30), (255, 240, 180)),
    'silver':  ((22, 24, 28), (210, 215, 225), (130, 136, 148), (250, 250, 255)),
    'copper':  ((28, 16, 10), (230, 140, 70), (150, 80, 40), (255, 210, 150)),
    'wine':    ((26, 10, 18), (220, 60, 100), (140, 30, 60), (255, 170, 190)),
    'berry':   ((22, 12, 26), (190, 80, 200), (110, 40, 130), (255, 190, 255)),
    'mint':    ((10, 26, 22), (80, 225, 180), (40, 140, 110), (220, 255, 240)),
    'lavender': ((22, 18, 34), (180, 150, 255), (110, 90, 180), (235, 225, 255)),
    'autumn':  ((28, 16, 8), (240, 140, 50), (190, 70, 30), (255, 220, 130)),
    'spring':  ((18, 26, 16), (140, 220, 90), (80, 150, 60), (250, 255, 200)),
    'summer':  ((26, 20, 8), (255, 210, 60), (240, 120, 50), (180, 240, 120)),
    'winter':  ((16, 22, 32), (200, 230, 250), (130, 160, 200), (255, 255, 255)),
    'desert':  ((34, 22, 14), (235, 180, 100), (180, 120, 60), (255, 235, 170)),
    'tropical': ((10, 28, 24), (40, 220, 160), (255, 190, 60), (170, 240, 220)),
    'coral':   ((28, 12, 16), (255, 110, 110), (200, 60, 80), (255, 220, 170)),
    'arctic':  ((14, 22, 30), (140, 200, 235), (80, 130, 180), (230, 245, 255)),
    'blood':   ((24, 8, 12), (235, 60, 70), (150, 25, 35), (255, 190, 160)),
    'deepsea': ((6, 14, 26), (30, 110, 150), (12, 60, 100), (90, 200, 220)),
    'earth':   ((24, 20, 14), (150, 120, 80), (90, 70, 45), (200, 180, 130)),
    'stone':   ((22, 22, 24), (160, 160, 165), (100, 100, 105), (210, 210, 215)),
    'steel':   ((18, 20, 24), (150, 170, 190), (90, 105, 125), (220, 230, 245)),
    'jade':    ((10, 24, 20), (60, 200, 150), (25, 120, 90), (200, 255, 230)),
    'amber':   ((30, 20, 8), (255, 180, 40), (190, 110, 20), (255, 235, 170)),
    'azure':   ((12, 20, 34), (80, 160, 255), (40, 90, 190), (200, 230, 255)),
    'space':   ((10, 10, 24), (140, 120, 255), (60, 200, 230), (255, 220, 160)),
    'violet':  ((20, 14, 30), (160, 90, 255), (90, 50, 170), (230, 200, 255)),
}


def _motif_waves(c, pal):
    """Волны: море, дюны, звук, вода."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(7)
    c.glow(310, 110, 62, acc, 95)
    c.circle(310, 110, 26, acc, a=225)
    for layer in range(6):
        y0 = 175 + layer * 52
        amp = 15 + layer * 7
        ph = rnd.uniform(0, 6.28)
        fr = 0.011 + 0.004 * (layer % 3)
        col = p1 if layer % 2 == 0 else p2
        pts = [(0, 460), (0, y0)]
        for x in range(0, 421, 8):
            y = (y0 + amp * math.sin(ph + x * fr)
                 + amp * 0.6 * math.sin(x * fr * 2.3 + ph * 2))
            pts.append((x, y))
        pts.append((420, 460))
        c.poly(pts, col, a=55 + layer * 30)
        for k in range(2, len(pts) - 1):
            c.set(pts[k][0], pts[k][1] + 1, acc, 80)


def _motif_terrain(c, pal):
    """Рельеф: дюны, горные хребты, карты."""
    _bg, p1, p2, acc = pal
    for i in range(9):
        y0 = 85 + i * 42
        amp = 16 + i * 6
        col = p1 if i % 2 else p2
        pts = [(0, 460), (0, y0)]
        for x in range(0, 421, 10):
            y = y0 + amp * (math.sin(x * 0.012 + i) * 0.6
                            + math.sin(x * 0.031 + i * 2.7) * 0.4)
            pts.append((x, y))
        pts.append((420, 460))
        c.poly(pts, col, a=45 + i * 23)
    c.set(390, 40, acc, 200)
    c.set(48, 60, acc, 140)
    c.set(200, 30, acc, 170)


def _motif_particles(c, pal):
    """Частицы: песчинки, атомы, пыль, зёрна."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(5)
    pts = []
    for _ in range(110):
        x, y = rnd.uniform(10, 410), rnd.uniform(10, 450)
        pts.append((x, y))
        r = rnd.uniform(1, 4.2)
        col = (p1, p2, acc)[rnd.randrange(3)]
        c.circle(x, y, r, col, a=rnd.randrange(70, 230))
    for _ in range(30):
        a1, a2 = rnd.choice(pts), rnd.choice(pts)
        d = math.hypot(a2[0] - a1[0], a2[1] - a1[1])
        if d < 80:
            c.line(a1[0], a1[1], a2[0], a2[1], p2, a=60, t=1)
    for _ in range(3):
        x, y = rnd.uniform(60, 360), rnd.uniform(60, 400)
        c.glow(x, y, 26, acc, 80)


def _motif_peaks(c, pal):
    """Вершины: горы, достижение, рост."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(12)
    c.glow(330, 100, 55, acc, 95)
    c.circle(330, 100, 22, acc, a=215)
    for (base, amp, col, alpha) in ((250, 90, p2, 120), (330, 130, p1, 175),
                                     (430, 170, acc, 60)):
        pts = [(0, 460), (0, base)]
        for x in range(0, 421, 42):
            pts.append((x, base - rnd.uniform(0.2, 1.0) * amp))
        pts.append((420, 460))
        c.poly(pts, col, a=alpha)


def _motif_flow(c, pal):
    """Потоки: ветер, реки, трафик, звуковые волны."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(3)
    for i in range(16):
        y0 = 30 + i * 27
        ph = rnd.uniform(0, 6.28)
        prev = None
        for t in range(51):
            x = t * 8.4
            y = y0 + 55 * math.sin(ph + t * 0.09) * (t / 51.0)
            if prev:
                c.line(prev[0], prev[1], x, y, p1 if i % 2 else p2, a=150, t=2)
            prev = (x, y)
        if i % 4 == 0:
            c.glow(prev[0], prev[1], 10, acc, 110)


def _motif_grid(c, pal):
    """Город: кварталы, окна, технологии, структура."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(9)
    c.glow(210, 66, 70, acc, 75)
    x = 8.0
    while x < 396:
        w = rnd.uniform(22, 46)
        h = rnd.uniform(80, 270)
        y0 = 452 - h
        c.rect(int(x), int(y0), int(w), int(h), p2, a=165)
        c.frame(int(x), int(y0), int(w), int(h), p1, t=1, a=210)
        wy = int(y0) + 8
        while wy < 446:
            wx = int(x) + 4
            while wx < int(x + w) - 3:
                if rnd.random() < 0.45:
                    c.set(wx, wy, acc, 190)
                wx += 10
            wy += 14
        x += w + rnd.uniform(4, 10)


def _motif_orbit(c, pal):
    """Орбиты: космос, атомы, циклы времени."""
    _bg, p1, p2, acc = pal
    c.stars(42, seed=4, c=(160, 170, 210))
    c.glow(210, 230, 62, acc, 105)
    c.circle(210, 230, 20, acc, a=235)
    for k in range(3):
        rx, ry = 58 + k * 55, 26 + k * 24
        for i in range(96):
            ang = 2 * math.pi * i / 96
            c.set(210 + rx * math.cos(ang), 230 + ry * math.sin(ang),
                  p1 if k % 2 == 0 else p2, 165)
        ang = 0.7 + k * 1.9
        px, py = 210 + rx * math.cos(ang), 230 + ry * math.sin(ang)
        c.glow(px, py, 15, p2, 115)
        c.circle(px, py, 6, acc, a=230)


def _motif_network(c, pal):
    """Сети: мозг, нейросети, связи, общество."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(21)
    nodes = [(rnd.uniform(30, 390), rnd.uniform(30, 430)) for _ in range(26)]
    for i, (x1, y1) in enumerate(nodes):
        for j, (x2, y2) in enumerate(nodes):
            if j <= i:
                continue
            if math.hypot(x2 - x1, y2 - y1) < 92:
                c.line(x1, y1, x2, y2, p2, a=70, t=1)
    for k, (x, y) in enumerate(nodes):
        col = acc if k % 4 == 0 else p1
        if k % 4 == 0:
            c.glow(x, y, 17, col, 95)
        c.circle(x, y, 3 if k % 3 else 5, col, a=225)


def _motif_flora(c, pal):
    """Флора: растения, экология, рост, питание."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(8)
    for i in range(7):
        x0 = 40 + i * 56
        h = rnd.uniform(160, 300)
        pts = []
        for t in range(41):
            tt = t / 40.0
            pts.append((x0 + 26 * math.sin(tt * 2.2 + i), 450 - h * tt))
        for k in range(len(pts) - 1):
            c.line(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1],
                   p1, a=205, t=2)
        for t in (0.35, 0.55, 0.75):
            lx, ly = pts[int(t * 40)]
            c.circle(lx + 12, ly, 7, p2, a=175)
            c.circle(lx - 12, ly + 4, 6, p2, a=150)
        c.circle(pts[-1][0], pts[-1][1], 9, acc, a=205)
    c.glow(210, 60, 50, acc, 60)


def _motif_flame(c, pal):
    """Пламя: огонь, энергия, тепло, страсть."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(19)
    c.glow(210, 330, 120, p1, 85)
    for (h, w, col, alpha) in ((300, 82, p2, 140), (215, 55, p1, 195),
                               (130, 32, acc, 235)):
        pts = []
        for i in range(13):
            t = i / 12.0
            pts.append((210 - w * math.sin(t * math.pi), 460 - h * t))
        for i in range(13):
            t = 1 - i / 12.0
            pts.append((210 + w * math.sin(t * math.pi) * 0.9, 452 - h * t * 0.96))
        c.poly(pts, col, a=alpha)
    for _ in range(16):
        x, y = rnd.uniform(140, 280), rnd.uniform(60, 240)
        c.circle(x, y, rnd.uniform(1, 2.5), acc, a=rnd.randrange(120, 230))


def _motif_crystal(c, pal):
    """Кристалл: алмазы, химия, искусство, иконография."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(15)
    c.glow(210, 225, 95, p1, 80)
    pts = [(210, 85), (302, 188), (264, 338), (156, 338), (118, 188)]
    c.poly(pts, p1, a=115)
    for (a1, b1) in ((pts[0], pts[2]), (pts[0], pts[3]), (pts[1], pts[4])):
        c.line(a1[0], a1[1], b1[0], b1[1], acc, a=205, t=2)
    for (x, y) in pts:
        c.circle(x, y, 4, acc, a=235)
    for (cx, cy, r) in ((80, 120, 16), (350, 300, 13), (330, 96, 9)):
        c.poly([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], p2, a=150)
    for _ in range(18):
        c.set(rnd.uniform(20, 400), rnd.uniform(20, 440), acc,
              rnd.randrange(120, 230))


def _motif_cells(c, pal):
    """Клетки: биология, медицина, микромир."""
    _bg, p1, p2, acc = pal
    rnd = random.Random(14)
    for _ in range(9):
        x, y = rnd.uniform(50, 370), rnd.uniform(50, 410)
        r = rnd.uniform(18, 36)
        c.circle(x, y, r, p1, a=52)
        for i in range(44):
            ang = 2 * math.pi * i / 44
            c.set(x + r * math.cos(ang), y + r * math.sin(ang), p1, 215)
        c.circle(x + r * 0.25, y - r * 0.2, r * 0.35, p2, a=205)
        for _ in range(5):
            ox, oy = rnd.uniform(-r * .6, r * .6), rnd.uniform(-r * .6, r * .6)
            c.circle(x + ox, y + oy, 2, acc, a=150)
    c.glow(210, 230, 80, acc, 45)


def _motif_spheres(c, pal):
    """Сферы: спорт, планеты, пузыри, глобальные темы."""
    _bg, p1, p2, acc = pal
    for (cx, cy, r, col) in ((140, 150, 62, p1), (300, 268, 74, p2),
                             (178, 352, 44, acc)):
        c.glow(cx, cy, r + 24, col, 60)
        c.circle(cx, cy, r, col, a=110)
        for i in range(64):
            ang = 2 * math.pi * i / 64
            c.set(cx + r * math.cos(ang), cy + r * math.sin(ang), col, 235)
        for off in (-0.42, 0.0, 0.42):
            rx = r * 0.42
            for i in range(36):
                ang = 2 * math.pi * i / 36
                c.set(cx + off * r + rx * math.cos(ang),
                      cy + r * 0.92 * math.sin(ang), _bg, 190)


def _motif_spiral(c, pal):
    """Спираль: галактики, циклы, философия, время."""
    _bg, p1, p2, acc = pal
    c.stars(38, seed=6, c=(170, 180, 220))
    for arm in range(2):
        col = (p1, p2)[arm]
        for i in range(160):
            t = i / 160.0
            ang = arm * math.pi + t * 4.6
            r = 14 + t * 165
            c.circle(210 + r * math.cos(ang) * 0.95,
                     235 + r * math.sin(ang) * 0.55,
                     3 if t < .6 else 2, col, a=200)
    c.glow(210, 235, 46, acc, 115)
    c.circle(210, 235, 12, acc, a=240)


ART_MOTIFS = {'waves': _motif_waves, 'terrain': _motif_terrain,
              'particles': _motif_particles, 'peaks': _motif_peaks,
              'flow': _motif_flow, 'grid': _motif_grid, 'orbit': _motif_orbit,
              'network': _motif_network, 'flora': _motif_flora,
              'flame': _motif_flame, 'crystal': _motif_crystal,
              'cells': _motif_cells, 'spheres': _motif_spheres,
              'spiral': _motif_spiral}

# Семантическая таблица: корни слов -> (мотив, палитра) или имя legacy-арта.
# Покрывает ~400 корней; для тем вне таблицы работает выбор Gemini или хэш.
ART_KEYWORDS = [
    (('песок', 'песчан', 'дюн', 'бархан', 'пустын', 'оазис', 'сахар',
      'пляж', 'берег', 'побереж'),
     ('terrain', 'sand')),
    (('море', 'океан', 'волн', 'прилив', 'отлив', 'сёрф', 'серф', 'коралл',
      'риф', 'подводн', 'акваланг', 'глубин', 'атлантик', 'тихий океан',
      'медуз', 'кит', 'акул', 'дельфин', 'рыб', 'цунами'),
     ('waves', 'ocean')),
    (('горы', 'горн', 'вершин', 'эверест', 'альпин', 'скал', 'каньон',
      'ущель', 'перевал'), ('peaks', 'stone')),
    (('вулкан', 'извержен', 'лава', 'магм'), ('flame', 'fire')),
    (('огонь', 'пожар', 'пламя', 'горен', 'костёр', 'костер'),
     ('flame', 'fire')),
    (('молни', 'гроза', 'гром', 'ураган', 'торнадо', 'циклон', 'буря'),
     ('flame', 'ice')),
    (('погод', 'метеоролог', 'осадк', 'дожд', 'снегопад', 'ветер',
      'циклон', 'прогноз погод'), ('flow', 'storm')),
    (('климат', 'потеплен', 'озон', 'выброс', 'парник'), ('flow', 'storm')),
    (('вод', 'речк', 'рек', 'озер', 'родник', 'водопад', 'гидро',
      'акведук', 'канал', 'море'), ('waves', 'azure')),
    (('эколог', 'природ', 'переработ', 'мусор', 'пластик', 'отход',
      'окружающ', 'загрязнен'), 'sprout'),
    (('лес', 'тайг', 'джунгл', 'амазонк', 'листв', 'роща', 'бор ', 'парк',
      'вырубк'), ('flora', 'forest')),
    (('растен', 'цвет', 'сад', 'ботаник', 'флор', 'посад', 'фертильн'),
     ('flora', 'spring')),
    (('животн', 'звер', 'млекопита', 'фаун', 'зоо', 'заповедн', 'красная книга'),
     ('terrain', 'forest')),
    (('птиц', 'орнит', 'пернат', 'ласточк', 'сокол', 'орел ', 'орёл'),
     ('flow', 'azure')),
    (('насеком', 'пчел', 'бабочк', 'муравь', 'энтомолог', 'жук'),
     ('particles', 'amber')),
    (('бактер', 'вирус', 'микроб', 'инфекц', 'пандем', 'эпидем', 'вакцин',
      'иммун', 'прививк', 'микробиолог'), ('cells', 'mint')),
    (('медиц', 'здоров', 'болезн', 'лечен', 'врач', 'больниц', 'аптек',
      'диагноз', 'симптом', 'фармац', 'таблетк'), ('cells', 'blood')),
    (('сердц', 'карди', 'инфаркт', 'артери', 'давлени', 'пульс',
      'электрокардио', 'сосуд', 'кров', 'тромб'), 'pulse'),
    (('мозг', 'нейрон', 'памят', 'мышлен', 'сн ', 'головн', 'интеллект'),
     ('network', 'violet')),
    (('хим', 'молекул', 'элемент', 'реакц', 'веществ', 'кислот',
      'менделеев', 'соединен'), ('crystal', 'jade')),
    (('атом', 'ядерн', 'радиоакт', 'изотоп', 'физик', 'квантов',
      'ньютон', 'эйнштейн', 'относительн', 'механик'), ('orbit', 'cyber')),
    (('биолог', 'клетк', 'генет', 'хромосом', 'наследств', 'эволюц',
      'дарвин', 'ген '), 'dna'),
    (('электр', 'энерг', 'батаре', 'заряд', 'напряж', 'розетк', 'генератор',
      'электростанц'), ('particles', 'amber')),
    (('истори', 'древн', 'эпох', 'цар', 'импер', 'революц', 'средневеков',
      'цивилизац', 'археолог', 'рим', 'греци', 'велик', 'войн', 'рыцар'),
     ('terrain', 'gold')),
    (('египт', 'пирамид', 'фараон', 'иероглиф', 'сфинкс'), ('peaks', 'sand')),
    (('архитектур', 'строительств', 'здан', 'сооружен', 'мост', 'башн',
      'проект', 'инженер'), ('grid', 'stone')),
    (('город', 'урбанист', 'метро', 'улиц', 'транспорт', 'пробк', 'дорог',
      'мегаполис'), ('grid', 'amber')),
    (('эконом', 'деньг', 'рынок', 'инфляц', 'банк', 'финанс', 'бюджет',
      'налог', 'кризис', 'валют', 'рубл', 'доллар', 'вклад', 'кредит',
      'торговл'), ('peaks', 'gold')),
    (('бизнес', 'компан', 'предпринимательств', 'стартап', 'менеджмент',
      'маркетинг', 'бренд', 'реклам'), ('grid', 'copper')),
    (('статист', 'график', 'диаграмм', 'показател', 'аналитик', 'данн',
      'исследован', 'опрос', 'процент'), 'chart'),
    (('програм', 'код', 'питон', 'python', 'алгоритм', 'разработк',
      'приложен', 'сайт', 'базы данных', 'скрипт'), 'code'),
    (('нейросет', 'искусствен', 'ии ', ' машинн обучен', 'чатгпт', 'chatgpt',
      'llm', 'гпт', 'deep'), 'neural'),
    (('робот', 'автоматизац', 'дрон', 'беспилот', 'искусствен'),
     'robot'),
    (('интернет', 'безопасн', 'парол', 'хакер', 'фишинг', 'скам',
      'конфиденциальн', 'шифрован', 'антивирус', 'кибербезопасн'), 'lock'),
    (('образован', 'школ', 'универ', 'урок', 'учител', 'учеб', 'знан',
      'экзамен', 'егэ', 'диплом', 'студент', 'наук'), 'book'),
    (('литератур', 'книг', 'писател', 'поэт', 'стих', 'роман', 'проз',
      'чтени', 'библиотек'), 'book'),
    (('язык', 'русск', 'английск', 'иностран', 'грамматик', 'перевод',
      'лингвист', 'слов'), 'book'),
    (('музык', 'песн', 'гитар', 'фортепиан', 'инструмент', 'концерт',
      'джаз', 'рок ', 'опер', 'нот ', 'звук'), ('waves', 'violet')),
    (('искусств', 'живопис', 'картин', 'художник', 'музе', 'скульптур',
      'дизайн', 'рисован', 'портрет', 'творчеств'), ('crystal', 'sunset')),
    (('кино', 'фильм', 'кинематограф', 'актер', 'актёр', 'режиссер',
      'сериал', 'оскар', 'мультфильм'), ('grid', 'storm')),
    (('театр', 'спектакл', 'сцен', 'балет', 'опетт', 'оперетт'),
     ('crystal', 'wine')),
    (('спорт', 'футбол', 'хоккей', 'баскетбол', 'олимпий', 'медал',
      'тренировк', 'соревнован', 'матч', 'турнир', 'чемпион'),
     ('spheres', 'mint')),
    (('зож', 'питани', 'диет', 'витамин', 'калорий', 'фитнес', 'бег ',
      'зарядк', 'йог'), ('flora', 'mint')),
    (('психолог', 'психик', 'эмоц', 'стресс', 'характер', 'личност',
      'мотивац', 'саморазвит', 'депресс'), ('network', 'lavender')),
    (('обществ', 'социолог', 'демограф', 'культур', 'народ', 'традиц'),
     ('network', 'stone')),
    (('полит', 'государств', 'власт', 'зако ', 'право', 'конституц',
      'парламент', 'выбор', 'президент', 'юрид'), ('grid', 'steel')),
    (('географ', 'геолог', 'рельеф', 'континент', 'стран', 'путешеств',
      'туризм', 'поход', 'экспедици', 'карт '), ('terrain', 'earth')),
    (('авиац', 'самолет', 'самолёт', 'летчик', 'лётчик', 'воздухоплаван',
      'аэропорт', 'вертолет'), ('flow', 'azure')),
    (('поезд', 'железн', 'вагон', 'вокзал', 'локомотив'), ('flow', 'steel')),
    (('автомобил', 'машин ', 'двигател', 'колес', 'бензин', 'мотор',
      'транспорт '), 'gear'),
    (('техник', 'механизм', 'станок', 'агрегат', 'промышленн', 'завод',
      'производств'), 'gear'),
    (('время', 'час ', 'времени', 'хронолог', 'историч'), ('orbit', 'silver')),
    (('мода', 'одежд', 'стил ', 'ткан', 'костюм', 'модел '),
     ('flow', 'berry')),
    (('фотограф', 'камер', 'снимок', 'фото', 'объектив'), ('crystal', 'mono')),
    (('кулинар', 'ед ', 'кухн', 'блюд', 'рецепт', 'повар', 'пищ',
      'готовить', 'вкус', 'продукт', 'овощ', 'фрукт', 'мяс', 'хлеб', 'пшениц',
      'урожай'), ('flora', 'gold')),
    (('кофе', 'чай ', 'напитк', 'какао', 'шоколад'), ('particles', 'amber')),
    (('математ', 'числ', 'формул', 'геометр', 'алгебр', 'уравнен', 'матан',
      'функци', 'теорем', 'пифагор'), ('crystal', 'cyber')),
    (('астроном', 'галакт', 'звезд', 'звёзд', 'созвезд', 'планет',
      'вселенн', 'космос', 'космонавт', 'астронавт', 'спутник', 'ракет',
      'орбит', 'луна', 'марс', 'невесом', 'nasa'), ('orbit', 'space')),
    (('нло', 'инопланет', 'уфо', 'пришельц'), ('orbit', 'space')),
    (('цифров', 'гаджет', 'смартфон', 'технолог', 'инновац', 'ит ',
      'будущ', 'футур', 'прогресс'), ('grid', 'cyber')),
    (('игр ', 'гейм', 'киберспорт', 'шахмат', 'настольн'), ('grid', 'wine')),
    (('религ', 'вера', 'бог ', 'церкв', 'храм', 'икон', 'ислам', 'буддиз',
      'христианств', 'духовн'), ('crystal', 'gold')),
    (('философ', 'этик', 'смысл', 'мудрост'), ('spiral', 'stone')),
    (('побед', 'достиж', 'успех', 'цель', 'рекорд'), ('peaks', 'gold')),
    (('стихия', 'землетряс', 'бедств', 'катаклизм'), ('waves', 'storm')),
]


# «Дружественные» палитры: когда у нескольких разделов совпадает мотив,
# цвета мягко чередуются — дюны остаются дюнами, но слайды не одинаковые.
_PAL_FRIENDS = {
    'sand': ('amber', 'autumn', 'earth'), 'desert': ('amber', 'autumn', 'earth'),
    'ocean': ('deepsea', 'azure', 'arctic'),
    'deepsea': ('ocean', 'azure', 'arctic'),
    'azure': ('ocean', 'deepsea', 'arctic'),
    'forest': ('spring', 'jade', 'mint'), 'spring': ('forest', 'jade', 'mint'),
    'jade': ('forest', 'spring', 'mint'), 'mint': ('jade', 'spring', 'forest'),
    'cyber': ('violet', 'space', 'steel'), 'violet': ('cyber', 'lavender', 'space'),
    'space': ('cyber', 'violet', 'steel'), 'gold': ('amber', 'copper', 'sand'),
    'amber': ('gold', 'autumn', 'sand'), 'copper': ('gold', 'amber', 'autumn'),
    'storm': ('steel', 'mono', 'space'), 'steel': ('storm', 'mono', 'space'),
    'mono': ('steel', 'storm', 'silver'), 'fire': ('sunset', 'berry', 'autumn'),
    'sunset': ('fire', 'coral', 'amber'), 'coral': ('sunset', 'tropical', 'berry'),
    'tropical': ('coral', 'forest', 'summer'),
    'lavender': ('violet', 'wine', 'space'), 'wine': ('berry', 'lavender', 'sunset'),
    'berry': ('wine', 'coral', 'sunset'), 'ice': ('arctic', 'azure', 'steel'),
    'arctic': ('ice', 'deepsea', 'azure'), 'blood': ('wine', 'fire', 'berry'),
    'earth': ('stone', 'autumn', 'sand'), 'stone': ('earth', 'steel', 'sand'),
    'autumn': ('amber', 'earth', 'copper'), 'dawn': ('sunset', 'coral', 'gold'),
    'summer': ('tropical', 'gold', 'amber'), 'winter': ('ice', 'arctic', 'azure'),
    'silver': ('mono', 'steel', 'arctic'),
}


def _kw_in(k, text):
    """Короткие ключи (<=4 симв.) ищем как отдельные слова, длинные — подстрокой."""
    if len(k) <= 4:
        return (' ' + k.strip() + ' ') in (' ' + text + ' ')
    return k in text


def choose_art(topic, title='', bullets=(), gemini_art=None):
    """Выбирает спек картинки для раздела: Gemini -> ключевые слова -> хэш.

    -> ('motif', 'palette') | имя legacy-арта ('neural', 'pulse', ...)."""
    if gemini_art:
        motif, palette = gemini_art
        if motif in ART_MOTIFS and palette in ART_PALETTES:
            return (motif, palette)
    text = normalize('%s %s %s' % (topic, title,
                                   ' '.join(str(b) for b in bullets)))
    best, best_n = None, 0
    for keys, spec in ART_KEYWORDS:
        n = sum(1 for k in keys if _kw_in(k, text))
        if n > best_n:
            best, best_n = spec, n
    if best:
        return best
    # Совсем незнакомая тема: уникальный, но стабильный узор из её хэша.
    h = zlib.crc32(text.encode('utf-8')) & 0xffffffff
    motif = ('waves', 'particles', 'crystal', 'network', 'spiral',
             'peaks')[h % 6]
    palette = ('sand', 'ocean', 'forest', 'gold', 'violet', 'coral',
               'cyber', 'autumn', 'storm', 'jade')[(h >> 8) % 10]
    return (motif, palette)


def render_art(spec):
    """PNG-байты 420x460 по спеку: ('motif','palette') или legacy-имя."""
    if isinstance(spec, str):
        if spec in _ART_PAINTERS:
            return art_png(spec)
        spec = (spec, 'cyber')
    motif, palette = spec[0], spec[1]
    painter = ART_MOTIFS.get(motif) or _motif_waves
    pal = ART_PALETTES.get(palette) or ART_PALETTES['cyber']
    key = 'gen:%s:%s' % (motif, palette)
    if key not in _ART_CACHE:
        cnv = PNGCanvas(420, 460, bg=pal[0])
        painter(cnv, pal)
        _ART_CACHE[key] = cnv.png()
    return _ART_CACHE[key]


# --- реальные фото по теме: Wikimedia / Openverse (без ключей и библиотек) ---


def _jpeg_size(data):
    """(ширина, высота) JPEG по маркерам SOF; None, если не разобралось."""
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            if w and h:
                return w, h
            return None
        if m in (0xD8, 0xD9, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
        else:
            i += 2 + ((data[i + 2] << 8) | data[i + 3])
    return None


def _src_rect(img, w, h):
    """Центрированная обрезка (srcRect) фото под прямоугольник слайда."""
    size = _jpeg_size(img)
    if not size:
        return None
    iw, ih = size
    target = float(w) / float(h)
    src = float(iw) / float(ih)
    if src <= 0 or abs(src / target - 1) < 0.08:
        return None
    if src > target:
        cut = int((1 - target / src) / 2 * 100000)
        return (cut, 0, cut, 0)
    cut = int((1 - src / target) / 2 * 100000)
    return (0, cut, 0, cut)


def _png_size(data):
    """(ширина, высота) PNG из заголовка IHDR; None, если не разобралось."""
    if data[:8] != b'\x89PNG\r\n\x1a\n' or len(data) < 24:
        return None
    w, h = struct.unpack('>II', data[16:24])
    return (w, h) if w and h else None


def _img_fit(img, x, y, w, h):
    """Картинка в прямоугольнике карточки: (x, y, w, h, src_rect).

    JPEG-фото заполняют карточку целиком — центр-обрезка srcRect.
    PNG (например, сгенерированные Gemini) вписываются без искажений
    пропорций по центру: у панели тёмная заливка, поля выглядят рамкой."""
    if img[:2] == b'\xff\xd8':
        return x, y, w, h, _src_rect(img, w, h)
    size = _png_size(img)
    if not size:
        return x, y, w, h, None
    iw, ih = size
    src = float(iw) / float(ih)
    target = float(w) / float(h)
    if src >= target:
        nw, nh = w, int(round(w / src))
    else:
        nh, nw = h, int(round(h * src))
    nw, nh = max(1, nw), max(1, nh)
    return x + (w - nw) // 2, y + (h - nh) // 2, nw, nh, None


# Доступность сети проверяется ОДИН раз (v5.1): если интернета нет,
# все онлайн-источники отключаются мгновенно, а не ждут таймауты.
_NET_STATE = {'ok': None}
# v7: кэш точных названий статей Википедии — «ии» -> «Искусственный
# интеллект» запоминается; повторные темы разрешаются мгновенно.
# Кэш содержания: повторная презентация по знакомой теме не ходит
# в сеть за текстом вовсе (фото всё равно ищутся заново, если надо).
_WIKI_TITLE_CACHE = {}          # (lang, тема_норм.) -> название | None
_CONTENT_CACHE = {'map': {}, 'order': []}   # тема -> content (LRU 12)


def net_available(timeout=5):
    """Есть ли интернет. Результат кэшируется до перезапуска.

    Сначала проверяем Википедию; если она недоступна (блокировка,
    сбой) — Wikimedia Commons. Если и он молчит, считаем сеть
    отсутствующей: фото подставляться не будет, но текст может."""
    if _NET_STATE['ok'] is None:
        for api in (_WIKI_API, 'https://commons.wikimedia.org/w/api.php'):
            try:
                req = urllib.request.Request(
                    api + '?action=query&meta=siteinfo&format=json',
                    headers={'User-Agent': _HTTP_UA})
                urllib.request.urlopen(req, timeout=timeout).read(1)
                _NET_STATE['ok'] = True
                break
            except urllib.error.HTTPError:
                _NET_STATE['ok'] = True   # сервер ответил — сеть есть
                break
            except Exception:
                continue   # попробуем запасной источник
        if _NET_STATE['ok'] is None:
            _NET_STATE['ok'] = False
    return _NET_STATE['ok']


class _SyncExclude(object):
    """Потокобезопасный набор уже использованных адресов фото (v6).

    Разделы презентации ищут фото ПАРАЛЛЕЛЬНО, и набор «занятых»
    адресов обязан проверяться и пополняться атомарно — иначе одна
    и та же фотография попадёт на два слайда."""

    def __init__(self):
        self._set = set()
        self._lock = threading.Lock()

    def claim(self, url):
        """Атомарно занимает адрес. -> True, если он был свободен."""
        with self._lock:
            if url in self._set:
                return False
            self._set.add(url)
            return True

    def __contains__(self, url):
        with self._lock:
            return url in self._set

    def add(self, url):
        with self._lock:
            self._set.add(url)


def _claim(exclude, url):
    """Занимает адрес фото в наборе исключений (set ИЛИ _SyncExclude)."""
    if isinstance(exclude, _SyncExclude):
        return exclude.claim(url)
    if url in exclude:
        return False
    exclude.add(url)
    return True


def fetch_commons_photos(query, want=1, exclude=None, min_w=640,
                         max_bytes=4 * 1024 * 1024):
    """Настоящие фото по теме с Wikimedia Commons -> [JPEG-байты, ...].

    Фото свободны, API без ключа. Возвращается уменьшенная копия (~900px).
    exclude — набор уже использованных адресов картинок: одна фотография
    не может попасть на два слайда. v6: кандидаты скачиваются
    ПАРАЛЛЕЛЬНО (первый успешный в порядке релевантности и попадает
    в выдачу), а не по одному — фото-этап ускоряется в разы."""
    out = []
    if _NET_STATE['ok'] is False:
        return out
    query = ' '.join(query.split())
    if not query:
        return out
    exclude = exclude if exclude is not None else set()
    url = ('https://commons.wikimedia.org/w/api.php?action=query&format=json'
           '&generator=search&gsrnamespace=6&gsrlimit=10'
           '&gsrsearch=%s&prop=imageinfo&iiprop=url|size|mime'
           '&iiurlwidth=900' % urllib.parse.quote('filetype:bitmap ' + query))
    try:
        data = _http_json_retry(url, timeout=7, retries=1)
        pages = list((data.get('query') or {}).get('pages', {}).values())
        pages.sort(key=lambda x: x.get('index', 99))
        cands = []
        for p in pages[:12]:
            ii = (p.get('imageinfo') or [{}])[0]
            if ii.get('mime') != 'image/jpeg':
                continue
            if int(ii.get('width') or 0) < min_w:
                continue
            thumb = ii.get('thumburl') or ii.get('url')
            if thumb:
                cands.append(thumb)
        # качаем сразу пачку: хватит первых успешных по порядку релевантности
        cands = cands[:max(want + 2, 4)][:8]

        def _grab(thumb):
            if not _claim(exclude, thumb):
                return None
            try:
                req = urllib.request.Request(thumb,
                                             headers={'User-Agent': _HTTP_UA})
                with urllib.request.urlopen(req, timeout=8) as r:
                    raw = r.read(max_bytes + 1)
                if len(raw) > max_bytes or raw[:2] != b'\xff\xd8':
                    return None
                return raw
            except Exception:
                return None

        if cands:
            with ThreadPoolExecutor(max_workers=min(4, len(cands))) as ex:
                for raw in ex.map(_grab, cands):
                    if raw:
                        out.append(raw)
                    if len(out) >= want:
                        break
    except Exception as e:
        log('Commons «%s»: %r' % (query, e))
    return out


def fetch_commons_photo(query, min_w=640, max_bytes=4 * 1024 * 1024):
    """Первое настоящее фото по теме с Commons -> JPEG-байты | None.

    Обёртка над fetch_commons_photos для простых проверок."""
    got = fetch_commons_photos(query, want=1, min_w=min_w, max_bytes=max_bytes)
    return got[0] if got else None


def _download_jpeg(url, max_bytes=4 * 1024 * 1024):
    """Скачивает картинку по URL; отдаёт JPEG-байты или None."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
        with urllib.request.urlopen(req, timeout=14) as r:
            raw = r.read(max_bytes + 1)
        if len(raw) > max_bytes or raw[:2] != b'\xff\xd8':
            return None
        return raw
    except Exception:
        return None


# служебные картинки статьи (иконки, схемы, флаги) нам не нужны
_SKIP_FILES = re.compile(
    r'(иконк|лого|логотип|флаг|герб|карта|расположени|схем|диаграмм|'
    r'question|book|commons-logo|wiki|pog|barnstar|stub|edit|arrow|'
    r'значок|эмблем|карточк|logo|icon|flag|map|diagram|seal)', re.IGNORECASE)


def wiki_resolve_title(topic, lang='ru'):
    """Тема -> точное название статьи Википедии. -> str | None.

    Починка «фото Иисуса на тему ИИ» (v5.2.2): opensearch ищет статьи
    по НАЧАЛУ названия и ранжирует их по популярности, поэтому короткая
    тема «ии» превращалась в статью «Иисус Христос» — самую читаемую
    на «Ии...». Теперь: 1) тема проверяется как ТОЧНОЕ название статьи
    или редиректа (короткие темы — ещё и ПРОПИСНЫМИ: «ии» -> редирект
    «ИИ» -> «Искусственный интеллект»); 2) если точного совпадения нет —
    обычный поиск по началу названия; 3) совсем короткие темы (до 3
    символов) без точного совпадения в Википедию не идут вовсе: надёжнее
    обойтись без её фото, чем взять случайную популярную статью на те
    же буквы."""
    if _NET_STATE['ok'] is False:
        return None
    topic = ' '.join(str(topic or '').split())
    if not topic:
        return None
    cache_key = (lang, normalize(topic))
    if cache_key in _WIKI_TITLE_CACHE:
        return _WIKI_TITLE_CACHE[cache_key]
    result = _wiki_resolve_title_net(topic, lang)
    # кэшируем и «нет статьи»: отрицательный ответ тоже стоит запроса
    if len(_WIKI_TITLE_CACHE) > 200:
        _WIKI_TITLE_CACHE.clear()
    _WIKI_TITLE_CACHE[cache_key] = result
    return result


def _wiki_resolve_title_net(topic, lang='ru'):
    api = 'https://%s.wikipedia.org/w/api.php' % lang
    # короткая тема без пробелов похожа на аббревиатуру: «ии» -> «ИИ»
    abbrev = len(topic) <= 4 and ' ' not in topic
    candidates = [topic] + ([topic.upper()] if abbrev else [])
    for cand in candidates:
        try:
            data = _http_json_retry(api + '?' + urllib.parse.urlencode(
                {'action': 'query', 'redirects': 1, 'titles': cand,
                 'format': 'json'}), timeout=7, retries=1)
            for page in ((data.get('query') or {}).get('pages')
                         or {}).values():
                title = page.get('title')
                if title and 'missing' not in page:
                    log('Википедия-%s: «%s» — точное совпадение «%s»'
                        % (lang, topic, title))
                    return title
        except Exception as e:
            log('Википедия-%s, точный поиск «%s»: %r' % (lang, cand, e))
            return None
    if len(topic) <= 3:
        log('Википедия-%s: «%s» — точной статьи нет, а поиск по началу '
            'названия для такой короткой темы ненадёжен, пропускаем'
            % (lang, topic))
        return None
    try:
        found = _http_json_retry(api + '?' + urllib.parse.urlencode(
            {'action': 'opensearch', 'search': topic, 'limit': 1,
             'format': 'json'}), timeout=7, retries=1)
        if found and found[1]:
            log('Википедия-%s: «%s» — по началу названия «%s»'
                % (lang, topic, found[1][0]))
            return found[1][0]
    except Exception as e:
        log('Википедия-%s, поиск «%s»: %r' % (lang, topic, e))
    return None


def fetch_wiki_photos(topic, want=8, min_w=500, lang='ru'):
    """НАСТОЯЩИЕ картинки из статьи Википедии по теме. -> [jpeg-байты, ...]

    Сначала тема превращается в ТОЧНОЕ название статьи (v5.2.2), затем
    берём все фотографии статьи (а не только заглавную): у темы «капуста»
    будут реальные снимки с грядки, у темы «Марс» — снимки планеты,
    у темы «ии» — картинки из «Искусственный интеллект», а не «Иисуса
    Христа». lang='en' ищет в английской Википедии — там статьи с фото
    есть почти для любой темы. v6: данные файлов и сами картинки
    качаются ПАРАЛЛЕЛЬНО (раньше — по одной, и это была самая долгая
    часть фото-этапа). Может вернуть пустой список."""
    out = []
    if _NET_STATE['ok'] is False:
        return out
    title = wiki_resolve_title(topic, lang=lang)
    if not title:
        return out
    api = 'https://%s.wikipedia.org/w/api.php' % lang
    try:
        data = _http_json_retry(api + '?' + urllib.parse.urlencode(
            {'action': 'query', 'prop': 'images', 'imlimit': 50,
             'redirects': 1, 'titles': title, 'format': 'json'}),
            timeout=7, retries=1)
        files = []
        for page in (data.get('query') or {}).get('pages', {}).values():
            for im in page.get('images') or []:
                t = str(im.get('title') or '')
                if re.search(r'\.jpe?g$', t, re.I) and not _SKIP_FILES.search(t):
                    files.append(t)
        files = list(dict.fromkeys(files))[:14]   # без повторов, порядок сохранён

        def _file_photo(fname):
            """imageinfo одного файла + скачивание. -> bytes | None."""
            try:
                d = _http_json_retry(api + '?' + urllib.parse.urlencode(
                    {'action': 'query', 'prop': 'imageinfo',
                     'iiprop': 'url|size|mime', 'iiurlwidth': 900,
                     'titles': fname, 'format': 'json'}),
                    timeout=7, retries=1)
                for page in (d.get('query') or {}).get('pages', {}).values():
                    ii = (page.get('imageinfo') or [{}])[0]
                    if ii.get('mime') != 'image/jpeg':
                        return None
                    if int(ii.get('width') or 0) < min_w:
                        return None
                    return _download_jpeg(ii.get('thumburl') or ii.get('url'))
            except Exception:
                return None
            return None

        if files:
            with ThreadPoolExecutor(max_workers=min(6, len(files))) as ex:
                for raw in ex.map(_file_photo, files):
                    if raw:
                        out.append(raw)
                    if len(out) >= want:
                        break
    except Exception as e:
        log('Фото Википедии-%s «%s»: %r' % (lang, topic, e))
    return out


def fetch_openverse_photo(query, exclude=None):
    """Фото из открытого агрегатора Openverse (CC-лицензии, без ключа).

    -> JPEG-байты | None. Дополняет Wikimedia: если там по теме пусто,
    пробуем Openverse (Flickr и другие коллекции)."""
    if _NET_STATE['ok'] is False:
        return None
    query = ' '.join(query.split())
    if not query:
        return None
    exclude = exclude if exclude is not None else set()
    url = ('https://api.openverse.org/v1/images/?format=json&page_size=12'
           '&mature=false&extension=jpg&q=%s'
           % urllib.parse.quote(query))
    try:
        data = _http_json(url, timeout=12)
        for item in (data.get('results') or [])[:8]:
            if str(item.get('mimetype') or '') not in ('image/jpeg', 'jpg'):
                continue
            try:
                if int(item.get('width') or 0) < 500:
                    continue
            except Exception:
                pass
            src = str(item.get('url') or '')
            if not src or not _claim(exclude, src):
                continue
            raw = _download_jpeg(src)
            if raw:
                return raw
    except Exception as e:
        log('Openverse «%s»: %r' % (query, e))
    return None


def fetch_flickr_photo(query, exclude=None):
    """Настоящее фото с Flickr (публичный фид, без ключа) по тегам.

    -> JPEG-байты | None. Фид отдаёт свежие публичные фото с заданными
    тегами — независимый от Wikimedia источник реальных снимков.
    Берём большой вариант (_b), если есть; иначе — средний (_m)."""
    if _NET_STATE['ok'] is False:
        return None
    query = ' '.join(query.split())
    if not query:
        return None
    exclude = exclude if exclude is not None else set()
    # из запроса делаем теги: слова 3+ буквы, латиница
    tags = [w for w in re.findall(r'[a-z]{3,}', query.lower())][:4]
    if not tags:
        return None
    url = ('https://www.flickr.com/services/feeds/photos_public.gne?'
           'tags=%s&tagmode=all&format=json&nojsoncallback=1'
           % urllib.parse.quote(','.join(tags)))
    try:
        data = _http_json(url, timeout=10)
        for item in (data.get('items') or [])[:8]:
            media = item.get('media') or {}
            small = str(media.get('m') or '')
            if not small:
                continue
            # большой вариант: _m.jpg -> _b.jpg (а иногда .gif — пропустим)
            big = re.sub(r'_m\.(jpg|jpeg)$', r'_b.\1', small,
                         flags=re.IGNORECASE)
            for src in (big, small):
                if not src or not _claim(exclude, src):
                    continue
                raw = _download_jpeg(src)
                if not raw:
                    continue
                # отсекаем слишком мелкие миниатюры (Flickr _m = 240px):
                # на слайде они выглядят размытыми
                sz = _jpeg_size(raw)
                if sz and min(sz) < 500:
                    continue
                return raw
    except Exception as e:
        log('Flickr «%s»: %r' % (query, e))
    return None


# ----------------------------------------------------------------------------
# Источники текста для слайдов: Gemini API -> Википедия -> база знаний (офлайн)
# ----------------------------------------------------------------------------

GEMINI_KEY_FILE = 'gemini_key.txt'
# Основная модель — gemini-3.5-flash-lite (v5.2.2, как просили): текст
# пишет именно она — быстрее отвечает и экономнее расходует квоту.
# Если Google не отдаст её данному ключу/региону (404/429), автоматически
# подставляется полноценная gemini-3.5-flash, затем алиасы «latest» и
# старые ветки. Использованная модель честно показывается в ответе
# ассистента и на финальном слайде.
GEMINI_MODELS = ('gemini-3.5-flash-lite', 'gemini-3.5-flash',
                 'gemini-flash-lite-latest', 'gemini-flash-latest',
                 'gemini-2.5-flash', 'gemini-2.0-flash')
# Кэш модели (v6): сработавшая модель идёт первой в следующий раз,
# а 404-модели (отключены Google) пропускаются до перезапуска —
# каждая попытка «мёртвой» модели это потерянные секунды.
_GEMINI_MODEL_STATE = {'ok': None, 'dead': set()}


def _gemini_model_order():
    """Порядок попытки моделей: рабочая первой, отключённые — в конце."""
    dead = _GEMINI_MODEL_STATE['dead']
    alive = [m for m in GEMINI_MODELS if m not in dead]
    first = _GEMINI_MODEL_STATE['ok']
    if first in alive:
        alive.remove(first)
        alive.insert(0, first)
    return alive
_WIKI_API = ('https://en.wikipedia.org/w/api.php' if LANG == 'en'
             else 'https://ru.wikipedia.org/w/api.php')
_HTTP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'RotoGoBeryllium/7.0 (personal desktop assistant)')

# Темы, которые ассистент знает офлайн (без интернета). Каждый тезис —
# проверяемый факт; формат раздела: (заголовок, [тезисы], картинка).
TOPIC_BASE = [
    {'keys': ('искусственный интеллект', 'ии', 'нейросети', 'нейросеть',
              'нейронные сети', 'машинное обучение', 'chatgpt', 'chat gpt',
              'гпт', 'ии и нейросети'),
     'title': 'Искусственный интеллект и нейросети', 'art': 'neural',
     'subtitle': 'Как машины научились решать задачи, которые раньше были доступны только человеку',
     'sections': [
         ('Что такое ИИ', [
             'Термин «искусственный интеллект» предложил Джон Маккарти в 1956 году',
             'Тест Тьюринга (1950): машину не отличить от человека в беседе',
             'Современный ИИ — машинное обучение: программа учится на примерах',
             'Прорыв глубокого обучения случился в 2012 году (сеть AlexNet)'], 'neural'),
         ('Как учатся нейросети', [
             'Нейросеть — сеть «нейронов»; её знания — это числа-веса',
             'Ошибка предсказания сравнивается с ответом, веса корректируются',
             'Трансформеры (2017, «Attention Is All You Need») — основа GPT и BERT',
             'Большие языковые модели обучают на триллионах слов'], 'chart'),
         ('Где ИИ уже работает', [
             'Перевод и голосовые помощники: Google Переводчик, Siri, Алиса',
             'Медицина: анализ снимков; AlphaFold предсказала 200 млн белков',
             'Автопилоты Tesla и Waymo; беспилотные такси уже возят пассажиров',
             'Генерация текста, картинок и музыки: ChatGPT, Midjourney, Suno'], 'robot'),
         ('Цифры и факты', [
             'ChatGPT набрал 100 млн пользователей за 2 месяца — рекорд',
             'Обучение флагманских моделей стоит десятки-сотни млн долларов',
             'Рынок ИИ, по оценкам аналитиков, превысит 1,8 трлн $ к 2030 году',
             'Основные вычисления для ИИ делают видеокарты (NVIDIA)'], 'globe'),
         ('Риски и этика', [
             'Галлюцинации: модель уверенно выдумывает факты и источники',
             'Предвзятость: ИИ наследует стереотипы из обучающих данных',
             'Дипфейки: подделка голоса и видео — инструмент мошенников',
             'Спорные вопросы: чьими текстами и картинками училась модель'], 'lock'),
         ('Что дальше', [
             'Мультимодальность: одна модель понимает текст, звук и видео',
             'ИИ-агенты: сами планируют и выполняют цепочки задач',
             'Европейский AI Act (2024) — первый закон о регулировании ИИ',
             'Главная задача — безопасный и предсказуемый ИИ'], 'dna'),
     ]},
    {'keys': ('python', 'питон', 'программирование', 'язык программирования',
              'программировать', 'код'),
     'title': 'Python и программирование', 'art': 'code',
     'subtitle': 'Язык №1 для новичков, аналитики данных и искусственного интеллекта',
     'sections': [
         ('Откуда взялся Python', [
             'Автор — Гвидо ван Россум, первая версия вышла в 1991 году',
             'Название — в честь «Летающего цирка Монти Пайтона», не змеи',
             'Философия — «Дзен Питона»: читаемость важнее хитрости',
             'Синтаксис простой: код читается почти как английский текст'], 'code'),
         ('Почему его выбирают', [
             'С 2021 года стабильно в топе рейтингов TIOBE и PYPL',
             'Сотни тысяч готовых библиотек почти на любую задачу',
             'Один язык — и для школьного проекта, и для сервера Google',
             'Огромное сообщество: ответ почти на любой вопрос уже есть'], 'chart'),
         ('Кто использует', [
             'Google, YouTube, Instagram, Netflix, Spotify, Dropbox',
             'NASA: обработка данных миссий и бортовые сценарии',
             'Наука и данные: NumPy, pandas, matplotlib, SciPy',
             'ИИ: PyTorch и TensorFlow — интерфейсы у них на Python'], 'globe'),
         ('Что можно написать', [
             'Сайты и API: Django, Flask, FastAPI',
             'Игры на Pygame и скрипты для автоматизации рутины',
             'Телеграм-боты, парсеры, десктопные утилиты',
             'Нейросети и анализ данных: Keras, scikit-learn'], 'book'),
         ('Сильные и слабые стороны', [
             'Плюсы: читаемость, библиотеки, сообщество, кроссплатформенность',
             'Минус: в чистом виде в 10–100 раз медленнее C++ и Rust',
             'Выход: тяжёлые вычисления на C/C++, Python их связывает',
             'Python 2 закрыт в 2020 году; актуальная ветка — Python 3'], 'gear'),
     ]},
    {'keys': ('космос', 'космонавтика', 'астрономия', 'вселенная', 'планеты',
              'солнечная система', 'звезды', 'звёзды', 'ракеты', 'ракета'),
     'title': 'Космос и Вселенная', 'art': 'rocket',
     'subtitle': 'От Большого взрыва до космических станций: как устроен мир за пределами Земли',
     'sections': [
         ('Вселенная в цифрах', [
             'Возраст Вселенной — около 13,8 млрд лет (Большой взрыв)',
             'Диаметр наблюдаемой Вселенной — примерно 93 млрд световых лет',
             'Обычное вещество — лишь ~5%; остальное — тёмная материя и энергия',
             'Ближайшая звезда после Солнца — Проксима Центавра: 4,2 световых года'], 'galaxy'),
         ('Солнечная система', [
             'Восемь планет; на Солнце приходится 99,86% массы системы',
             'Свет от Солнца идёт до Земли 8 минут 20 секунд',
             'У Юпитера почти сотня спутников; у Сатурна — кольца из льда',
             'Год на Меркурии длится всего 88 земных суток'], 'planets'),
         ('Человек в космосе', [
             'Юрий Гагарин, 12 апреля 1961 года: один виток за 108 минут',
             'Алексей Леонов, 1965 год: первый выход в открытый космос',
             '«Аполлон-11», 20 июля 1969 года: Армстронг и Олдрин на Луне',
             'МКС летает с 1998 года: ~400 км высоты, ~27 600 км/ч'], 'rocket'),
         ('Далёкие рубежи', [
             'Вояджер-1 (старт 1977) ушёл на 24+ млрд км, покинул гелиосферу',
             'Телескоп «Джеймс Уэбб» (2021) смотрит в инфракрасном свете',
             'Марсоходы Curiosity и Perseverance ищут следы жизни',
             'Программа «Артемида» готовит новые высадки на Луну'], 'book'),
         ('Почему летать сложно', [
             'Чтобы остаться на орбите, нужна скорость 7,9 км/с',
             'До 90% стартовой массы ракеты — топливо',
             'В невесомости атрофируются мышцы: нужна ежедневная зарядка',
             'Многоразовые ракеты SpaceX снизили цену запуска в разы'], 'gear'),
     ]},
    {'keys': ('экология', 'природа', 'климат', 'изменение климата',
              'окружающая среда', 'переработка', 'экологии', 'экологию'),
     'title': 'Экология и климат', 'art': 'sprout',
     'subtitle': 'Что происходит с планетой — и что реально может сделать каждый',
     'sections': [
         ('Климат меняется', [
             'Планета потеплела примерно на 1,2 °C с доиндустриальной эпохи',
             'CO2 в атмосфере: было ~280 ppm, сейчас — более 420 ppm',
             '2023 год стал самым тёплым за историю наблюдений',
             'Парижское соглашение (2015): удержать потепление в 1,5–2 °C'], 'sprout'),
         ('Пластик и океаны', [
             'В океан ежегодно попадает 8–11 млн тонн пластика',
             'Пластик разлагается сотни лет, распадаясь на микропластик',
             'Микропластик находят даже в питьевой воде и крови',
             'Большой тихоокеанский мусорный участок — около 1,6 млн км²'], 'globe'),
         ('Леса и живая природа', [
             'Мир теряет около 10 млн гектаров леса в год',
             'Амазония — крупнейший тропический лес планеты',
             'С 1970 года популяции позвоночных сократились почти на 70%',
             'Каждый день из-за вырубки и загрязнения исчезают виды'], 'book'),
         ('Что уже делают в мире', [
             'Более 30% мировой электроэнергии дают ВИЭ (2023 год)',
             'Солнечные панели — самый дешёвый источник электричества',
             'Электромобили — около 18% продаж авто в мире (2023)',
             'Страны вводят углеродные налоги и лимиты на выбросы'], 'chart'),
         ('Что можешь ты', [
             'Сортировать отходы: переплавка банки экономит ~95% энергии',
             'Экономить электричество: светодиоды тратят его в разы меньше',
             'Меньше одноразового: своя бутылка, сумка, термокружка',
             'Местные продукты и меньше перелётов — меньше выбросов'], 'pulse'),
     ]},
    {'keys': ('роботы', 'робот', 'робототехника', 'дроны', 'дрон'),
     'title': 'Роботы и робототехника', 'art': 'robot',
     'subtitle': 'От механических рук на конвейере до гуманоидов: как машины учатся работать',
     'sections': [
         ('От слова к машине', [
             'Слово «робот» — из пьесы К. Чапека R.U.R. (1920): robota',
             'Законы робототехники придумал Айзек Азимов в 1942 году',
             'Unimate (1961) — первый промышленный робот, у General Motors',
             'Сегодня робот — это механика + сенсоры + программы ИИ'], 'robot'),
         ('Какие бывают роботы', [
             'Промышленные манипуляторы: сварка, покраска, сборка',
             'Дроны: съёмка, доставка, поиск людей',
             'Бытовые: роботы-пылесосы и газонокосилки',
             'Гуманоиды (Atlas, Optimus) и роботы-хирурги da Vinci'], 'gear'),
         ('Роботы сегодня', [
             'В мире работает около 4 млн промышленных роботов',
             'Больше половины — в автопроме и электронике',
             'Робот не устаёт и не отвлекается: брак снижается в разы',
             'Автоматизация линии обычно окупается за 1–2 года'], 'chart'),
         ('Сенсоры и «мозг»', [
             'Лидары и камеры дают роботу «зрение»',
             'ИИ распознаёт предметы и людей в реальном времени',
             'SLAM: карта помещения и позиция строятся одновременно',
             'Планировщик прокладывает безопасную траекторию'], 'neural'),
         ('Этика и будущее', [
             'Роботы заберут рутину, но изменят рынок труда',
             'Экзоскелеты помогают медикам и грузчикам',
             'Решения о жизни и смерти должен принимать человек',
             'Робот — инструмент; важны цели, которые ставят люди'], 'lock'),
     ]},
    {'keys': ('безопасность', 'кибербезопасность', 'безопасность в интернете',
              'интернет безопасность', 'защита данных', 'хакеры', 'взлом'),
     'title': 'Безопасность в интернете', 'art': 'lock',
     'subtitle': 'Как защитить аккаунты, данные и деньги — простыми шагами',
     'sections': [
         ('Пароли', [
             'Длина важнее хитрости: 12+ символов надёжнее «P@ssw0rd!»',
             'Для каждого сайта — свой пароль',
             'Менеджер паролей помнит всё за вас',
             'Двухфакторная защита (2FA) — второй замок на аккаунт'], 'lock'),
         ('Фишинг и обман', [
             'Главное оружие хакеров — не вирусы, а обман людей',
             'Проверяйте адрес сайта: буквы в нём могут быть подменены',
             'Код из SMS не должен знать никто — ни «банк», ни «поддержка»',
             '«Вы выиграли!» — почти всегда ловушка'], 'globe'),
         ('Шифрование', [
             'HTTPS — замочек в адресной строке: трафик зашифрован',
             'Мессенджеры со сквозным шифрованием защищают переписку',
             'Публичный Wi-Fi без VPN — как разговор на площади',
             'Пароль от Wi-Fi в кафе не защищает ваш трафик'], 'code'),
         ('Главные угрозы', [
             'Вирусы-шифровальщики блокируют файлы и требуют выкуп',
             'Утечки баз: свой e-mail можно проверить на haveibeenpwned.com',
             'Подозрительные вложения — классическая дверь для вирусов',
             'Обновления закрывают найденные дыры: не откладывайте их'], 'chart'),
         ('Цифровая гигиена', [
             'Резервные копии по правилу 3-2-1: три копии, два носителя',
             'Меньше личных данных на публике: след не стирается',
             'Отдельная почта для регистраций и покупок',
             'Раз в год — аудит: у каких приложений есть доступ'], 'gear'),
     ]},
    {'keys': ('здоровье', 'зож', 'спорт', 'здоровый образ жизни', 'фитнес',
              'питание', 'зарядка'),
     'title': 'Здоровье и спорт', 'art': 'pulse',
     'subtitle': 'Простые правила с доказанным эффектом — без модных диет',
     'sections': [
         ('Движение — жизнь', [
             'ВОЗ: 150–300 минут умеренной нагрузки в неделю',
             '7–9 тысяч шагов в день — реальная польза для сердца',
             'Силовые тренировки дважды в неделю — мышцы и кости',
             'Сидячий день длиннее 8 часов — риск для сердца и спины'], 'pulse'),
         ('Сон', [
             'Взрослому нужно 7–9 часов сна',
             'Ложиться и вставать лучше в одно и то же время',
             'Экран за час до сна мешает выработке мелатонина',
             'Спальня: темнота, тишина и прохлада'], 'dna'),
         ('Питание', [
             'ВОЗ: минимум 400 г овощей и фруктов в день',
             'Сахар — меньше 10% дневных калорий',
             'Вода: примерно 30 мл на кг веса тела',
             'Режим важнее диет: есть регулярно и не наедаться на ночь'], 'sprout'),
         ('Проверки', [
             'Давление, пульс, кровь и сахар — хотя бы раз в год',
             'Стоматолог — раз в полгода',
             'Вакцинация — не только про детей',
             'Раннюю болезнь лечить проще и дешевле'], 'chart'),
         ('Покой и голова', [
             'Хронический стресс бьёт по сердцу и иммунитету',
             'Прогулка 20 минут заметно снижает тревожность',
             'Общение и хобби — часть здоровья, а не роскошь',
             'Телефон тоже заслуживает выходной'], 'galaxy'),
     ]},
]


def match_topic(topic):
    """Ищет тему во встроенной базе знаний (нечётко, терпит опечатки)."""
    t = normalize(topic)
    if not t:
        return None
    best = (0.0, None)
    for e in TOPIC_BASE:
        for k in e['keys']:
            if k == t or k in t or t in k:
                return e
            if len(k) > 4 and len(t) > 4:
                s = sim(k, t)
                if s > best[0]:
                    best = (s, e)
    return best[1] if best[0] >= 0.62 else None


def _sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _clip(s, n=130):
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(' ,;:') + '…'


def _http_json(url, timeout=8, data=None, headers=None):
    h = {'User-Agent': _HTTP_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _http_json_retry(url, timeout=8, retries=1, delay=1.2,
                     data=None, headers=None):
    """HTTP GET JSON с одним повтором при 429/403 Too Many Reqs.

    Wikimedia иногда троттлит IP (короткая вспышка запросов), и один
    повтор через пару секунд проходит. На обычной домашней сети это
    практически не нужно, но спасает при плотных вызовах."""
    last = None
    for attempt in range(retries + 1):
        try:
            return _http_json(url, timeout=timeout, data=data, headers=headers)
        except urllib.error.HTTPError as e:
            last = e
            if attempt < retries and e.code in (403, 429):
                time.sleep(delay)
                continue
            raise
        except Exception:
            raise
    raise last


_SKIP_WIKI = ('см. также', 'примечания', 'литература', 'ссылки', 'сноски',
              'источники', 'см также')


def _wiki_to_content(title, extract):
    """Превращает plain-текст статьи Википедии в разделы слайдов."""
    parts = extract.split('\n\n')
    intro = re.sub(r'\s+', ' ', parts[0])
    sents = _sentences(intro)
    subtitle = _clip(sents[0], 150) if sents else ''
    secs, cur_title, buf = [], None, []
    for part in parts[1:]:
        first = part.split('\n', 1)[0].strip()
        if re.match(r'^=+\s*.+?\s*=+$', first):
            if cur_title and buf:
                secs.append((cur_title, ' '.join(buf)))
            cur_title = re.sub(r'^=+\s*|\s*=+$', '', first)
            buf = [part.split('\n', 1)[1]] if '\n' in part else []
        else:
            buf.append(part)
    if cur_title and buf:
        secs.append((cur_title, ' '.join(buf)))
    sections = []
    for (h, txt) in secs:
        hl = h.lower().strip()
        if any(s in hl for s in _SKIP_WIKI) or len(txt) < 150:
            continue
        sentences = _sentences(re.sub(r'\s+', ' ', txt))
        lead = _clip(sentences[0], 200) if sentences else None
        bs = []
        for s in sentences[1:] if lead else sentences:
            if len(s) >= 25:
                bs.append(_clip(s, 160))
            if len(bs) == 6:
                break
        if len(bs) >= 2:
            sections.append([h[0].upper() + h[1:] if h else h, bs, None,
                             lead])
    if len(sections) < 2:
        return None
    return {'title': title, 'subtitle': subtitle, 'sections': sections,
            'chips': [], 'conclusions': [],
            'source': 'Википедия (реальные факты)', 'art': None}


def wiki_content(topic):
    """Текст слайдов из Википедии. -> content | None (нет сети или статьи).

    Тема сначала разрешается в ТОЧНОЕ название статьи (v5.2.2): «ии» ->
    «Искусственный интеллект», а не «Иисус Христос», как было при
    поиске по началу названия."""
    if _NET_STATE['ok'] is False:
        return None
    title = wiki_resolve_title(topic)
    if not title:
        return None
    try:
        data = _http_json(_WIKI_API + '?' + urllib.parse.urlencode(
            {'action': 'query', 'prop': 'extracts', 'explaintext': 1,
             'redirects': 1, 'titles': title, 'format': 'json'}))
        for page in data.get('query', {}).get('pages', {}).values():
            extract = page.get('extract', '') or ''
            if len(extract) >= 400:
                return _wiki_to_content(title, extract)
            return None
    except Exception as e:
        log('Википедия недоступна: %r' % e)
    return None


# Почему Gemini не ответил (для честного сообщения пользователю).
# prio — вес причины: гео/ключ (3) важнее лимита (2) и прочих кодов (1),
# чтобы сообщение от живой модели не затиралось отказом устаревшей.
_GEMINI_STATUS = {'warn': None, 'prio': 0}


def gemini_key():
    try:
        with open(os.path.join(_script_dir(), GEMINI_KEY_FILE), encoding='utf-8') as f:
            k = f.read().strip()
        return k or None
    except Exception:
        return None


def save_gemini_key(key):
    with open(os.path.join(_script_dir(), GEMINI_KEY_FILE), 'w', encoding='utf-8') as f:
        f.write(key.strip())


def _extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    a, b = text.find('{'), text.rfind('}')
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except Exception:
        return None


def gemini_content(topic, n_sections):
    """Текст слайдов от Google Gemini (нужен gemini_key.txt). -> content | None.

    v6: ОДИН вызов вместо двух — в этом же ответе модель возвращает
    английские поисковые запросы для фото (раньше их спрашивали
    отдельным запросом photo_queries, это 5-20 секунд сверху).
    Запросы возвращаются в content['pq'] в формате
    {'topic': [...], 'sections': {'0': [...]}}."""
    _GEMINI_STATUS['warn'] = None
    _GEMINI_STATUS['prio'] = 0
    key = gemini_key()
    if not key:
        return None
    if _NET_STATE['ok'] is False:
        return None
    prompt = (
        'Ты готовишь содержание учебной презентации на русском языке. '
        'Тема: «%s». Составь %d разделов. Ответь СТРОГО JSON без пояснений '
        'и без markdown: '
        '{"title": "короткое название", '
        '"subtitle": "одно предложение о сути темы", '
        '"chips": ["факт-чип 1", "факт-чип 2", "факт-чип 3"], '
        '"conclusions": ["вывод 1", "вывод 2", "вывод 3", "вывод 4"], '
        '"sections": [{"title": "заголовок раздела", '
        '"lead": "вводное предложение раздела (до 160 символов)", '
        '"bullets": ["тезис 1", "тезис 2", "тезис 3", "тезис 4", '
        '"тезис 5", "тезис 6"], '
        '"motif": "мотив из списка", "palette": "палитра из списка"}], '
        '"photo_queries": {"topic": ["english search query 1", '
        '"english search query 2"], '
        '"sections": {"0": ["english query for section 0"], '
        '"1": ["english query for section 1"]}}}. '
        'photo_queries — короткие АНГЛИЙСКИЕ запросы (1-3 слова, '
        'конкретные существительные) для поиска РЕАЛЬНЫХ ФОТОГРАФИЙ '
        'темы и каждого раздела в Wikimedia Commons: там описания '
        'на английском. Ключ sections — порядковый номер раздела. '
        'Мотивы иллюстраций (выбирай ПО СМЫСЛУ раздела): '
        'waves (волны, море, дюны, звук), terrain (рельеф, карты, история), '
        'particles (частицы, зёрна, атомы, песок), peaks (горы, рост, достижения), '
        'flow (потоки, ветер, реки, трафик), grid (город, структура, технологии), '
        'orbit (космос, атомы, циклы), network (сети, мозг, связи), '
        'flora (растения, экология, питание), flame (огонь, энергия), '
        'crystal (кристаллы, химия, искусство), cells (биология, медицина), '
        'spheres (спорт, планеты, глобальное), spiral (галактики, циклы, философия). '
        'Палитры: sand, ocean, forest, fire, ice, sunset, dawn, storm, cyber, '
        'mono, gold, silver, copper, wine, berry, mint, lavender, autumn, '
        'spring, summer, winter, desert, tropical, coral, arctic, blood, '
        'deepsea, earth, stone, steel, jade, amber, azure, space, violet. '
        'Требования: только проверяемые факты, конкретные числа, годы и имена; '
        'тезисы — по одному предложению до 150 символов, 5-7 штук на раздел; '
        'чипы до 30 символов; выводы до 120 символов; без воды и банальностей.'
        % (topic, n_sections))
    if LANG == 'en':
        prompt = ('Write ALL content (title, subtitle, chips, conclusions, '
                  'section titles, leads and bullets) in English. '
                  + prompt)
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'temperature': 0.6,
                                            'maxOutputTokens': 8192}}).encode('utf-8')
    for model in _gemini_model_order():
        try:
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   '%s:generateContent?key=%s' % (model, urllib.parse.quote(key)))
            data = _http_json(url, timeout=30, data=body,
                              headers={'Content-Type': 'application/json'})
            text = ''
            for part in data['candidates'][0]['content']['parts']:
                # «Думающие» модели добавляют служебные части — берём ответ.
                if part.get('text') and not part.get('thought'):
                    text = part['text']
                    break
            obj = _extract_json(text) if text else None
            if not obj:
                continue
            secs = []
            for sec in obj.get('sections', []):
                bs = [str(b).strip() for b in sec.get('bullets', [])
                      if str(b).strip()][:7]
                if sec.get('title') and len(bs) >= 2:
                    lead = str(sec.get('lead') or '').strip() or None
                    motif = str(sec.get('motif') or '').strip().lower()
                    palette = str(sec.get('palette') or '').strip().lower()
                    gart = ((motif, palette)
                            if motif in ART_MOTIFS and palette in ART_PALETTES
                            else None)
                    secs.append([_clip(str(sec['title']).strip(), 60),
                                 [_clip(str(b), 160) for b in bs],
                                 gart,
                                 _clip(lead, 200) if lead else None])
            if len(secs) >= 2:
                chips = [_clip(str(x).strip(), 40) for x in obj.get('chips', [])
                         if str(x).strip()][:3]
                concl = [_clip(str(x).strip(), 140)
                         for x in obj.get('conclusions', [])
                         if str(x).strip()][:5]
                # v6: английские фото-запросы из ТОГО ЖЕ ответа
                pq = _clean_photo_queries(obj.get('photo_queries'))
                _GEMINI_MODEL_STATE['ok'] = model
                return {'title': _clip(str(obj.get('title') or topic).strip(), 70),
                        'subtitle': _clip(str(obj.get('subtitle') or '').strip(), 160),
                        'chips': chips, 'conclusions': concl,
                        'sections': secs, 'pq': pq,
                        'source': 'Google Gemini (%s)' % model, 'art': None}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode('utf-8', 'replace')
            except Exception:
                detail = ''
            if 'location is not supported' in detail:
                warn, prio = ('Google отклонил запрос из этой сети '
                              '(Gemini API работает не во всех '
                              'странах и не через все VPN)'), 3
            elif e.code in (401, 403) or 'API key' in detail:
                warn, prio = ('ключ отклонён — проверьте его на '
                              'aistudio.google.com'), 3
            elif e.code == 429:
                warn, prio = ('лимит запросов Gemini исчерпан — подождите '
                              'минуту-другую (квота бесплатного ключа '
                              'небольшая)'), 2
            elif e.code == 404:
                warn, prio = ('модель отключена Google — нужна более '
                              'новая версия программы'), 1
                _GEMINI_MODEL_STATE['dead'].add(model)
            else:
                warn, prio = 'Gemini ответил ошибкой %s' % e.code, 1
            if prio >= _GEMINI_STATUS['prio']:
                _GEMINI_STATUS['warn'] = warn
                _GEMINI_STATUS['prio'] = prio
            log('Gemini %s: HTTP %s %s' % (model, e.code, detail[:200]))
        except Exception as e:
            if _GEMINI_STATUS['prio'] < 1:
                _GEMINI_STATUS['warn'] = ('Gemini не ответил '
                                          '(сбой сети или формат ответа)')
                _GEMINI_STATUS['prio'] = 1
            log('Gemini %s не ответил: %r' % (model, e))
    if _GEMINI_STATUS['warn'] is None:
        _GEMINI_STATUS['warn'] = 'Gemini вернул ответ не в том формате'
    return None


# ---------------------------------------------------------------------------
# Картинки строго по теме (v5.2): Gemini переводит тему в английские
# поисковые запросы, фото ищутся в 5 источниках (русская и английская
# Википедия, Wikimedia Commons, Openverse, Flickr). Без генерации:
# только настоящие фотографии; абстрактный арт — лишь для офлайн-режима.
# ---------------------------------------------------------------------------


def _clean_photo_queries(obj):
    """Чистит photo_queries из ответа Gemini -> dict | {}.

    {'topic': ['query', ...] (до 2), 'sections': {'0': [...]}} —
    индексы разделов строковые, запросы латиницей, до 60 символов."""
    if not isinstance(obj, dict):
        return {}
    clean = {}
    for k, v in obj.items():
        if k == 'topic':
            qs = [_clip(str(q).strip(' "\'').lower(), 60)
                  for q in (v if isinstance(v, list) else [])]
            clean['topic'] = [q for q in qs if q][:2]
        elif k == 'sections' and isinstance(v, dict):
            clean['sections'] = {}
            for idx, lst in v.items():
                qs = [_clip(str(q).strip(' "\'').lower(), 60)
                      for q in (lst if isinstance(lst, list) else [])]
                qs = [q for q in qs if q][:2]
                if qs and str(idx).isdigit():
                    clean['sections'][str(idx)] = qs
    return clean


def photo_queries(topic, section_titles=()):
    """ЗАПАСНОЙ отдельный вызов Gemini для фото-запросов (v6: основной
    путь — photo_queries внутри ответа gemini_content, этот функция
    остаётся для случаев, когда текст дал не Gemini, а ключ живой).

    -> dict | {}: {'topic': [...], 'sections': {'0': [...]}}"""
    key = gemini_key()
    if not key or _NET_STATE['ok'] is False:
        return {}
    secs = [str(s).strip() for s in section_titles if str(s).strip()][:8]
    prompt = (
        'Тема презентации: «%s». Заголовки её разделов: %s. '
        'Придумай поисковые запросы НА АНГЛИЙСКОМ языке для поиска '
        'реальных фотографий (Wikimedia Commons / Openverse): короткие '
        'конкретные существительные, 1-3 слова, без кавычек, по СМЫСЛУ '
        'темы и каждого раздела. Ответь СТРОГО JSON без markdown: '
        '{"topic": ["query 1", "query 2"], "sections": '
        '{"0": ["query"], "1": ["query"]}} — по 1-2 запроса на тему '
        'и ровно по одному на каждый раздел, ключ — порядковый номер.'
        % (topic, json.dumps(secs, ensure_ascii=False)))
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'temperature': 0.2,
                                            'maxOutputTokens': 8192}}).encode('utf-8')
    for model in _gemini_model_order():
        try:
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   '%s:generateContent?key=%s' % (model, urllib.parse.quote(key)))
            data = _http_json(url, timeout=25, data=body,
                              headers={'Content-Type': 'application/json'})
            text = ''
            for part in data['candidates'][0]['content']['parts']:
                if part.get('text') and not part.get('thought'):
                    text = part['text']
                    break
            obj = _extract_json(text) if text else None
            if not isinstance(obj, dict):
                continue
            clean = _clean_photo_queries(obj)
            if clean.get('topic') or clean.get('sections'):
                log('Поисковые запросы фото (%s): topic=%r sections=%r'
                    % (model, clean.get('topic'), clean.get('sections')))
                return clean
        except urllib.error.HTTPError as e:
            log('photo_queries %s: HTTP %s' % (model, e.code))
        except Exception as e:
            log('photo_queries %s: %r' % (model, e))
    return {}


# какие намерения разрешено выполнять по подсказке Gemini
# (опасные — очистка чата, выход, работа с ключом — исключены)
_ALLOWED_GI = ('search', 'open_app', 'open_folder', 'weather',
               'create_folder', 'create_presentation', 'create_file',
               'note', 'time', 'date', 'joke', 'system', 'help',
               'rates', 'calc', 'timer', 'translate', 'create_xlsx',
               'find_file', 'coin_dice')


def gemini_intent(raw):
    """Пытается понять нестандартную формулировку с помощью Gemini.

    Вызывается, когда встроенный парсер команд не смог. Быстрый запрос,
    температура 0. -> (имя_интента, аргумент) | None."""
    key = gemini_key()
    if not key or _NET_STATE['ok'] is False:
        return None
    prompt = _gp(
        ('Ты — определитель намерений русского ассистента Windows. '
         'Отнеси фразу пользователя к одной из команд и верни ТОЛЬКО JSON '
         'без пояснений и без markdown: {"intent": "имя", "arg": "аргумент"}\n'
         'Команды и аргументы:\n'
         'search — поиск в интернете (arg: поисковый запрос)\n'
         'open_app — открыть программу или сайт (arg: название)\n'
         'open_folder — открыть папку (arg: имя папки)\n'
         'weather — погода (arg: пусто)\n'
         'create_folder — создать папку (arg: имя папки)\n'
         'create_presentation — сделать презентацию PowerPoint (arg: тема)\n'
         'create_file — создать текстовый документ или файл Word '
         '(arg: тема; если просили именно Word — начни со слова «ворд»)\n'
         'note — короткая заметка в файл (arg: текст заметки)\n'
         'time / date / joke / system / help — время, дата, анекдот, '
         'характеристики ПК, список команд (arg: пусто)\n'
         'Если фраза — не команда, а болтовня или вопрос не по теме, '
         'верни {"intent": "unknown", "arg": ""}.\n'
         'Фраза пользователя: «%s»' % raw[:300]),
        ('You are the intent classifier of a Windows assistant. '
         'Map the user phrase to one of the commands and return ONLY JSON '
         'with no explanation and no markdown: {"intent": "name", "arg": "argument"}\n'
         'Commands and arguments:\n'
         'search — web search (arg: search query)\n'
         'open_app — open an app or site (arg: name)\n'
         'open_folder — open a folder (arg: folder name)\n'
         'weather — weather (arg: empty)\n'
         'create_folder — create a folder (arg: folder name)\n'
         'create_presentation — make a PowerPoint presentation (arg: topic)\n'
         'create_file — create a text document or Word file '
         '(arg: topic; if Word was explicitly asked, start with "word")\n'
         'note — short note to a file (arg: note text)\n'
         'time / date / joke / system / help — time, date, joke, '
         'PC specs, command list (arg: empty)\n'
         'If the phrase is not a command but chat or an off-topic question, '
         'return {"intent": "unknown", "arg": ""}.\n'
         'User phrase: "%s"' % raw[:300]))
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'temperature': 0.0,
                                            'maxOutputTokens': 512}}).encode('utf-8')
    for model in _gemini_model_order():
        try:
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   '%s:generateContent?key=%s' % (model, urllib.parse.quote(key)))
            data = _http_json(url, timeout=12, data=body,
                              headers={'Content-Type': 'application/json'})
            text = ''
            for part in data['candidates'][0]['content']['parts']:
                if part.get('text') and not part.get('thought'):
                    text = part['text']
                    break
            obj = _extract_json(text) if text else None
            if not obj:
                continue
            name = str(obj.get('intent') or '').strip().lower()
            if name in _ALLOWED_GI:
                return name, str(obj.get('arg') or '').strip()
            return None
        except Exception as e:
            log('Gemini-интент %s: %r' % (model, e))
            continue
    return None


def gemini_translate(text):
    """v7: перевод фразы через Gemini. -> str | None.

    Короткий запрос; модель — рабочая из кэша. Если в тексте кириллица,
    переводим на английский, иначе — на русский (пользователь русский)."""
    key = gemini_key()
    if not key or _NET_STATE['ok'] is False:
        return None
    has_cyr = bool(re.search(r'[а-я]', normalize(text)))
    if LANG == 'en':
        target = 'English' if has_cyr else 'Russian'
        prompt = ('Translate the text to %s. Reply ONLY with the translation, '
                  'no explanations or quotes.\nText:\n%s'
                  % (target, text[:1500]))
    else:
        target = 'английский' if has_cyr else 'русский'
        prompt = ('Переведи текст на %s язык. Ответь ТОЛЬКО переводом, '
                  'без пояснений и кавычек.\nТекст:\n%s'
                  % (target, text[:1500]))
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'temperature': 0.1,
                                            'maxOutputTokens': 2048}}).encode('utf-8')
    for model in _gemini_model_order():
        try:
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   '%s:generateContent?key=%s' % (model, urllib.parse.quote(key)))
            data = _http_json(url, timeout=25, data=body,
                              headers={'Content-Type': 'application/json'})
            for part in data['candidates'][0]['content']['parts']:
                if part.get('text') and not part.get('thought'):
                    t = part['text'].strip()
                    if t:
                        _GEMINI_MODEL_STATE['ok'] = model
                        return t
        except Exception as e:
            log('Gemini-перевод %s: %r' % (model, e))
            continue
    return None


def base_content(topic, n_sections=None):
    e = match_topic(topic)
    if not e:
        return None
    secs = list(e['sections'])
    if n_sections:
        # базы не хватает до заказанного числа слайдов — дополняем
        # универсальными секциями (с конца: факты, риски, итоги)
        want = max(3, min(6, n_sections))
        have = {s[0] for s in secs}
        for g in reversed(generic_content(topic, 6)['sections']):
            if len(secs) >= want:
                break
            if g[0] not in have:
                secs.append(g)
                have.add(g[0])
    return {'title': e['title'], 'subtitle': e['subtitle'],
            'sections': secs,
            'source': 'встроенная база знаний (офлайн)', 'art': e['art']}


def generic_content(topic, n_sections=6):
    """Последний рубеж: тема не из базы и интернет молчит.

    v5.0.1: каркас не хуже геминиевского текста — лид-абзац и 5-6
    тезисов в каждой секции, факты-чипы на титул, выводы в финале.
    Секций столько, сколько нужно под заказ (до шести). Картинка —
    не «книжка», а подбор по смыслу темы (choose_art)."""
    t = topic[0].upper() + topic[1:] if topic else 'Тема'
    n_sections = max(3, min(6, n_sections))
    pool = [
        ('Что это такое',
         ['Что такое %s: определение и суть' % t,
          'Откуда это появилось и как развивалось',
          'Ключевые термины простыми словами',
          'С чем тему часто путают — и чем она отличается',
          'Почему тема важна именно сейчас'],
         None,
         '%s проще понять от определения — и дальше идти по шагам: как устроено и где применяется.' % t),
        ('Как это устроено',
         ['Главные части и их назначение',
          'Как это работает — по шагам',
          'Какие идеи и законы лежат в основе',
          'Похожие подходы и альтернативы',
          'Что изменилось с приходом новых технологий'],
         None,
         'Любая тема раскрывается через устройство: из каких частей состоит и по каким правилам живёт.'),
        ('Где применяется',
         ['Типичные задачи и сценарии использования',
          'Отрасли и профессии, где это важно',
          'Известные примеры и кейсы',
          'Что востребовано прямо сейчас',
          'Где тема только начинает развиваться'],
         None,
         'Ценность темы — в применении: задачи, отрасли и профессии, где она встречается каждый день.'),
        ('Плюсы, минусы, риски',
         ['Сильные стороны и главные преимущества',
          'Слабые места и ограничения',
          'Частые ошибки новичков',
          'Когда подход не подходит',
          'Как снизить риски на практике'],
         None,
         'Взрослый взгляд на тему: сильные стороны рядом со слабыми местами и подводными камнями.'),
        ('Интересные факты',
         ['Самое неожиданное из того, что известно о теме',
          'Цифры и рекорды, связанные с темой',
          'Известные люди и их связь с темой',
          'Мифы о теме, которые давно опровергнуты',
          'Как тема отражена в культуре и языке'],
         None,
         'Тема оживает в деталях: факты, цифры и истории, которые запоминаются лучше определений.'),
        ('Итоги и что дальше',
         ['Главное о теме «%s» — сформулируйте суть одним предложением' % t,
          'Что изучить глубже: два-три направления по теме',
          'Где проверять факты: первоисточники, книги, открытые данные',
          'С чем тему «%s» часто путают — и как не ошибиться' % t,
          'Один небольшой практический шаг можно сделать уже сегодня'],
         None,
         'Короткий финал: главное о теме «%s» и разумные шаги для тех, '
         'кто хочет разобраться глубже.' % t),
    ]
    return {
        'title': t, 'art': None,
        'subtitle': ('Автономный режим: интернет и Gemini недоступны —'
                     ' универсальный каркас, наполните его фактами'),
        'chips': ['Определение и суть', 'Как устроено', 'Применение'],
        'conclusions': [
            'Каркас универсален: наполните его фактами по вашей теме',
            'Ключевые направления уже расписаны по разделам',
            'Структура подходит для школы, вуза и рабочей защиты',
            'Подключите ключ Gemini — и текст напишет модель'],
        'sections': pool[:n_sections],
        'source': 'универсальный каркас (тема не из базы, интернета нет)'}


def _norm_content(c):
    """Приводит любой источник к единому виду: разделы [заголовок, тезисы,
    арт, лид], плюс чипы и выводы (если источники их не дали — пусто)."""
    out = []
    for sec in c.get('sections', []):
        sec = list(sec) + [None] * max(0, 4 - len(sec))
        out.append([sec[0], [str(b) for b in sec[1]][:7], sec[2], sec[3]])
    c['sections'] = out
    c.setdefault('chips', [])
    if not c['chips']:
        # чипов нет (база или вики) — собираем из заголовков первых секций
        c['chips'] = [_clip(str(s[0]).strip(), 30) for s in out[:3] if s[0]]
    c.setdefault('conclusions', [])
    c.setdefault('subtitle', '')
    return c


def content_for(topic, n_slides=8):
    """Собирает содержание: Gemini (если есть ключ) -> Википедия -> база -> каркас.

    v7: кэш по теме (LRU 12) — повторный документ/презентация по знакомой
    теме не ходят в сеть за текстом; Gemini не тратит квоту дважды."""
    key = normalize(topic)
    if key in _CONTENT_CACHE['map']:
        _CONTENT_CACHE['order'].remove(key)
        _CONTENT_CACHE['order'].append(key)
        return _norm_content(_CONTENT_CACHE['map'][key])
    got = _content_for_net(topic, n_slides)
    if got and got.get('source', '').startswith(('Google', 'Википедия')):
        # офлайн-источники не кэшируем: они и так мгновенны
        if len(_CONTENT_CACHE['order']) >= 12:
            old = _CONTENT_CACHE['order'].pop(0)
            _CONTENT_CACHE['map'].pop(old, None)
        _CONTENT_CACHE['map'][key] = got
        _CONTENT_CACHE['order'].append(key)
    return got


def _content_for_net(topic, n_slides=8):
    n_want = max(3, min(6, n_slides - 2))
    for getter, arg in ((gemini_content, (topic, n_want)),
                        (wiki_content, (topic,))):
        try:
            c = getter(*arg)
        except Exception as e:
            log('Источник %s: %r' % (getattr(getter, '__name__', '?'), e))
            c = None
        if c:
            base = match_topic(topic)
            if base:
                c['art'] = base['art']
            if getter is not gemini_content and gemini_key() \
                    and _GEMINI_STATUS['warn']:
                c['gemini_warn'] = _GEMINI_STATUS['warn']
            return _norm_content(c)
    c = base_content(topic, n_want) or generic_content(topic, n_want)
    if gemini_key() and _GEMINI_STATUS['warn']:
        c['gemini_warn'] = _GEMINI_STATUS['warn']
    return _norm_content(c)


def parse_slide_count(raw):
    """«…на 10 слайдов» / «из семи слайдов» -> число или None."""
    t = normalize(raw)
    m = re.search(r'(?:на|из|в)\s+(\d{1,2})\s+(?:слайд|страниц)', t)
    if m:
        return int(m.group(1))
    words = 'пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать'
    m = re.search(r'(?:на|из|в)\s+(%s)\s+(?:слайд|страниц)' % words, t)
    if m:
        return {'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8, 'девять': 9,
                'десять': 10, 'одиннадцать': 11, 'двенадцать': 12}[m.group(1)]
    return None


def build_presentation(topic, path, n_slides=8, content=None, photos=None):
    """Собирает премиальную презентацию и ЗАПИСЫВАЕТ файл.

    Структура слайда-раздела: заголовок, лид-абзац, 5-7 тезисов, картинка.
    Титул: название, подзаголовок, 3 факта-чипа, картинка. Финал: выводы.
    Картинки: настоящие фото по теме (JPEG, photos={индекс: байты}) из
    пяти источников; при их отсутствии — генеративная иллюстрация под
    смысл раздела (без AI-генерации фото).

    Возвращает (число_слайдов, источник_текста, число_картинок, число_фото).
    Raises — при ошибке записи (честная ошибка, без выдуманного успеха)."""
    if content is None:
        content = content_for(topic, n_slides)
    photos = photos or {}
    # страховка типов: в photos должны лежать только байты картинки
    # (если источник вернул список — берём первый элемент)
    photos = {k: (v[0] if isinstance(v, (list, tuple)) and v else v)
              for k, v in photos.items() if v}
    topic = topic.strip().strip('«»"\'')
    t_cap = (topic[:1].upper() + topic[1:]) if topic else 'Презентация'
    big_title = content.get('title') or t_cap
    date_str = datetime.date.today().strftime('%d.%m.%Y')
    secs = list(content['sections'])
    n_sections = max(3, min(n_slides - 2, len(secs)))
    secs = secs[:n_sections]
    total = n_sections + 2
    chips = [str(c) for c in (content.get('chips') or []) if str(c).strip()][:3]
    concl = [str(c) for c in (content.get('conclusions') or [])
             if str(c).strip()][:5]
    if not concl:
        concl = [_clip(sec[1][0], 140) for sec in secs if sec[1]][:5]

    p = MiniPPTX()

    # одинаковый мотив у нескольких разделов -> чередуем палитры-друзей:
    # дюны остаются дюнами, но слайды не получаются близнецами
    seen_specs = {}

    def _vary(spec):
        if not isinstance(spec, tuple):
            return spec
        cnt = seen_specs.get(spec, 0)
        seen_specs[spec] = cnt + 1
        if not cnt:
            return spec
        pals = _PAL_FRIENDS.get(spec[1])
        return (spec[0], pals[(cnt - 1) % len(pals)]) if pals else spec

    # --- 1. титульный слайд: название, подзаголовок, чипы, фото/арт ---
    s = p.add_slide()
    p.rect(s, 0, 0, 170000, 6858000, grad=('00F0FF', 'FF2EC8', 5400000))
    p.ellipse(s, 6700000, 380000, 1300000, 1300000, line='00F0FF', alpha=25000)
    ph = photos.get(-1)
    p.card(s, 8000000, 1250000, 3550000, 4250000, fill='121A33', line='00F0FF')
    if ph:
        px, py, pw, pht, sr = _img_fit(ph, 8280000, 1550000,
                                       2990000, 3650000)
        p.picture(s, px, py, pw, pht, ph, key='photo:title', src_rect=sr)
    else:
        spec = _vary(choose_art(topic, big_title,
                                content.get('subtitle') or ''))
        p.picture(s, 8280000, 1550000, 2990000, 3650000, render_art(spec),
                  key='art:title:%s' % (spec,))
    p.text(s, 620000, 1750000, 6900000, 1600000,
           [{'runs': [(_clip(big_title, 60), 4000, 1, 'FFFFFF')], 'spc': 112}])
    p.rect(s, 640000, 3500000, 2400000, 75000, grad=('00F0FF', 'FF2EC8'))
    p.text(s, 620000, 3720000, 7000000, 700000,
           [{'runs': [(_clip(content.get('subtitle') or
                             'Обзор темы: факты, примеры и выводы', 180),
                       1500, 0, '9AA0B5')], 'spc': 135}])
    for j, chip in enumerate(chips):
        cx = 620000 + j * 2400000
        # текст чипов — белый (читается идеально), цвет — только в рамке
        acc = ACCENTS[j % len(ACCENTS)]
        p.card(s, cx, 4500000, 2250000, 720000, fill='141B33', line=acc,
               line_w=12700)
        p.text(s, cx + 80000, 4500000, 2090000, 720000,
               [{'runs': [(_clip(chip, 32), 1200, 1, 'F2F2F8')],
                 'align': 'ctr', 'spc': 118}], anchor='ctr')
    p.text(s, 620000, 6250000, 6700000, 400000,
            [{'runs': [('RotoGo Beryllium v%s  ·  %s'
                       % (APP_VERSION, date_str), 1100, 0, '5A6078')]}])

    # --- 2..N. содержательные слайды: лид + 5-7 тезисов + фото/арт ---
    for idx, sec in enumerate(secs):
        title, bullets, art, lead = (list(sec) + [None, None])[:4]
        acc = ACCENTS[idx % len(ACCENTS)]
        s = p.add_slide()
        p.rect(s, 0, 0, 120000, 6858000, fill=acc)
        p.text(s, 700000, 380000, 10900000, 800000,
               [{'runs': [(_clip(title, 56), 2700, 1, 'FFFFFF')]}])
        p.rect(s, 720000, 1310000, 2000000, 55000, grad=('00F0FF', 'FF2EC8'))
        top = 1490000
        if lead:
            # ширина — как у тезисов: лид не должен заезжать под карточку
            # с картинкой (картинка рисуется поверх и закрывала текст)
            p.text(s, 700000, top, 7000000, 700000,
                   [{'runs': [(_clip(lead, 200), 1300, 0, '9AA0B5')],
                     'spc': 130}])
            top += 720000
        # тезисы крупнее, когда их мало (до 5) — читаемость с задних рядов
        bsz = 1500 if len(bullets[:7]) <= 5 else 1400
        paras = []
        for j, b in enumerate(bullets[:7]):
            paras.append({'runs': [('•  ', bsz, 1, acc),
                                   (_clip(str(b), 160), bsz, 0, 'E8E8F0')],
                          'spc': 142, 'before': 0 if j == 0 else 700})
        if paras:
            p.text(s, 700000, top, 7000000, max(800000, 6350000 - top), paras)
        ph = photos.get(idx)
        p.card(s, 8050000, 1450000, 3450000, 4250000, fill='121A33', line=acc)
        if ph:
            px, py, pw, pht, sr = _img_fit(ph, 8330000, 1730000,
                                           2890000, 3690000)
            p.picture(s, px, py, pw, pht, ph, key='photo:%d' % idx,
                      src_rect=sr)
        else:
            if isinstance(art, tuple) and len(art) == 2:
                spec = art
            elif isinstance(art, str) and art in _ART_PAINTERS:
                spec = art
            else:
                spec = choose_art(topic, title, bullets)
            spec = _vary(spec)
            p.picture(s, 8330000, 1730000, 2890000, 3690000,
                      render_art(spec), key='art:%d:%s' % (idx, spec))
        p.text(s, 700000, 6480000, 7000000, 350000,
               [{'runs': [(_clip(t_cap, 40), 1100, 0, '5A6078')]}])
        p.text(s, 10100000, 6480000, 1300000, 350000,
               [{'runs': [('%d / %d' % (idx + 2, total), 1100, 0, '5A6078')],
                 'align': 'r'}])

    # --- финальный слайд: благодарность + выводы ---
    s = p.add_slide()
    p.rect(s, 0, 0, 12192000, 130000, grad=('00F0FF', 'FF2EC8'))
    p.ellipse(s, 9500000, 640000, 1600000, 1600000, line='7B2EFF', alpha=36000)
    p.ellipse(s, 1050000, 4600000, 1100000, 1100000, line='00F0FF', alpha=36000)
    p.text(s, 800000, 480000, 10600000, 900000,
           [{'runs': [('Спасибо за внимание!', 3200, 1, 'FFFFFF')],
             'align': 'ctr'}], anchor='ctr')
    p.rect(s, 4800000, 1500000, 2600000, 80000, grad=('00F0FF', 'FF2EC8'))
    p.text(s, 800000, 1720000, 10600000, 550000,
           [{'runs': [('Главное из презентации', 1800, 1, '00F0FF')],
             'align': 'ctr'}])
    paras = []
    for j, ccl in enumerate(concl[:5]):
        paras.append({'runs': [('—  ', 1400, 1, 'FF2EC8'),
                               (_clip(str(ccl), 140), 1400, 0, 'E8E8F0')],
                      'spc': 150, 'before': 0 if j == 0 else 800})
    if paras:
        p.text(s, 2300000, 2400000, 7600000, 3400000, paras)
    p.text(s, 800000, 6100000, 10600000, 400000,
            [{'runs': [('RotoGo Beryllium v%s  ·  текст: %s'
                       % (APP_VERSION, content['source']),
                       1100, 0, '5A6078')], 'align': 'ctr'}])

    p.save(path)
    n_photos = sum(1 for v in photos.values() if v)
    return total, content['source'], len(p.media), n_photos


def safe_filename(name, default='Презентация'):
    n = re.sub(r'[\\/:*?"<>|]+', ' ', name)
    n = re.sub(r'\s+', ' ', n).strip(' .')
    n = n[:48].strip()
    return n or default


# слова, которые не склоняются (винительный = именительный)
_INVARIANT_ENDU = ('кенгуру', 'судоку', 'гуру', 'меню', 'интервью', 'резюме')


def nominative(topic):
    """«про капусту» -> «капуста»: аккуратный заголовок и имя файла.

    Эвристика для винительного падежа («сделай презентацию про капусту»).
    Латиница, несклоняемые слова и всё остальное не трогаются."""
    t = (topic or '').strip()
    if not t or not re.match(r'^[а-яёА-ЯЁ ]+$', t):
        return t
    tl = t.lower()
    for w in _INVARIANT_ENDU:
        if tl.endswith(w):
            return t
    if tl.endswith('ию') and len(tl) > 4:
        return t[:-2] + 'ия'
    if tl.endswith('у') and len(tl) > 4:
        return t[:-1] + 'а'
    if tl.endswith('ю') and len(tl) > 4:
        return t[:-1] + 'я'
    return t


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for i in range(2, 100):
        p = '%s (%d)%s' % (base, i, ext)
        if not os.path.exists(p):
            return p
    return path


# ----------------------------------------------------------------------------
# «Мозг» ассистента — разбор и выполнение команд (без GUI, тестируемый)
# ----------------------------------------------------------------------------

def _pairs(words):
    """[(оригинал, нормализация)] без пустых слов."""
    out = []
    for w in words:
        n = normalize(w)
        if n:
            out.append((w, n))
    return out


def extract_location(pairs):
    """Вытаскивает из аргумента место сохранения.

    -> (loc, оставшиеся_пары), где loc:
       None | ('desktop',) | ('documents',) | ('last',) | ('folder', имя)

    Понимает ЛЮБЫЕ падежи: «в папку X», «в папке X», «в каталог/директорию
    X», «в новую папку X», «в ней», «в этой папке», «тут», «в документах»,
    «на рабочем столе»/«на столе» (v5.0: раньше винительный падеж «в папку»
    не распознавался — и файл уезжал на рабочий стол вместо папки)."""
    loc = None
    out = []
    i = 0
    n = len(pairs)
    folder_words = ('папку', 'папке', 'папки', 'каталог', 'каталоге',
                    'каталогу', 'директорию', 'директории')
    adj = ('новую', 'новой', 'новый', 'новая', 'мою', 'мой', 'эту', 'свою')
    while i < n:
        w = pairs[i][1]
        nxt = pairs[i + 1][1] if i + 1 < n else ''
        nxt2 = pairs[i + 2][1] if i + 2 < n else ''
        handled = False
        if w == 'в':
            if nxt in folder_words and nxt2:
                j = i + 2
                handled = True
            elif nxt in adj and nxt2 in folder_words and i + 3 < n:
                # «в новую папку X», «в мою папку X»
                j = i + 3
                handled = True
            elif (nxt2 in folder_words and nxt and nxt not in folder_words
                    and nxt not in adj
                    and nxt not in ('этой', 'это', 'той', 'нашей', 'моей',
                                    'своей')):
                # «в капуста папке» — имя сказано ПЕРЕД словом «папка»
                name = pairs[i + 1][0].strip(' «»"\'')
                if name:
                    loc = ('folder', name)
                i += 3
                continue
        elif i == 0 and w in folder_words and nxt:
            # «папку X» без предлога и в самом начале аргумента —
            # глагол команды уже отрезан («сделай презентацию папку отчеты»).
            # Внутри темы («про папки и файлы») НЕ срабатывает.
            j = i + 1
            handled = True
        if handled:
            while j < n and pairs[j][1] in adj:
                j += 1
            name = []
            while j < n and pairs[j][1] not in ('про', 'о', 'об', 'на'):
                name.append(pairs[j][0])
                j += 1
            if name:
                loc = ('folder', ' '.join(name).strip(' «»"\''))
            i = j
            continue
        if w == 'в':
            if nxt == 'ней':
                loc = ('last',)
                i += 2
                continue
            if nxt == 'этой' and nxt2 == 'папке':
                loc = ('last',)
                i += 3
                continue
            if nxt == 'документах':
                loc = ('documents',)
                i += 2
                continue
        if w == 'тут':
            loc = ('last',)
            i += 1
            continue
        if w == 'на':
            if nxt == 'рабочем' and nxt2 == 'столе':
                loc = ('desktop',)
                i += 3
                continue
            if nxt == 'столе':
                loc = ('desktop',)
                i += 2
                continue
        out.append(pairs[i])
        i += 1
    return loc, out


def strip_topic_prefix(pairs):
    """Убирает «про», «о», «об», «на тему», «по теме» в начале."""
    if not pairs:
        return pairs
    if pairs[0][1] == 'на' and len(pairs) > 1 and pairs[1][1] == 'тему':
        return pairs[2:]
    if pairs[0][1] == 'по' and len(pairs) > 1 and pairs[1][1] == 'теме':
        return pairs[2:]
    if pairs[0][1] in ('про', 'о', 'об', 'насчет'):
        return pairs[1:]
    return pairs


# "мусорные" слова в начале имени папки и темы
_FILLER_WORDS = ('новую', 'новый', 'новая', 'новое', 'мою', 'мой', 'моя',
                 'мое', 'просто', 'еще', 'ещё', 'мне', 'пжл', 'пожалуйста')

# слова-маркеры формата — выкидываются из темы документа
# («создай текстовый документ про AI» -> тема «AI»)
_FILE_WORDS = ('текстовый', 'текстового', 'текстовой', 'текстовое', 'текстовом',
               'файл', 'файла', 'файлу', 'файле', 'документ', 'документа',
               'документу', 'документе', 'txt', 'тхт', 'ворд', 'word', 'docx',
               'вордовский', 'doc')


def _strip_filler(pairs):
    i = 0
    while i < len(pairs) and pairs[i][1] in _FILLER_WORDS:
        i += 1
    return pairs[i:]


def _write_txt(content, path):
    """Пишет документ в .txt (UTF-8 с BOM — блокнот покажет без квадратиков)."""
    lines = [content.get('title') or '']
    if content.get('subtitle'):
        lines.append(content['subtitle'])
    lines.append('=' * 64)
    for i, sec in enumerate(content.get('sections', []), 1):
        title, bullets, _art, lead = (list(sec) + [None, None])[:4]
        lines.append('')
        lines.append('%d. %s' % (i, title))
        if lead:
            lines.append(lead)
        for b in bullets:
            lines.append('  • %s' % b)
    if content.get('conclusions'):
        lines.append('')
        lines.append('ИТОГИ')
        for c in content['conclusions']:
            lines.append('  — %s' % c)
    lines.append('')
    lines.append('RotoGo Beryllium v%s · %s · текст: %s'
                 % (APP_VERSION,
                    datetime.date.today().strftime('%d.%m.%Y'),
                    content.get('source', '')))
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(lines))


def _write_docx(content, path, topic):
    """Пишет документ в настоящий .docx (открывается в Word и LibreOffice)."""
    d = MiniDOCX()
    d.para(content.get('title') or topic, sz=52, bold=True, color='0D0D1A',
           after=140)
    if content.get('subtitle'):
        d.para(content['subtitle'], sz=24, color='5A6078', after=80)
    d.para('RotoGo Beryllium v%s · %s · текст: %s'
           % (APP_VERSION, datetime.date.today().strftime('%d.%m.%Y'),
              content.get('source', '')), sz=16, color='8A90A5', after=320)
    for i, sec in enumerate(content.get('sections', []), 1):
        title, bullets, _art, lead = (list(sec) + [None, None])[:4]
        d.para('%d. %s' % (i, title), sz=30, bold=True, color='3A2E8C',
               before=260, after=110)
        if lead:
            d.para(lead, sz=22, color='44445E', after=110)
        for b in bullets:
            d.bullet(str(b))
    if content.get('conclusions'):
        d.para('Итоги', sz=30, bold=True, color='3A2E8C', before=300, after=110)
        for c in content['conclusions']:
            d.bullet(str(c), mark='—')
    d.save(path)


class Assistant(object):
    def __init__(self):
        self.awaiting = None       # 'pptx_topic' | 'folder_name' | 'note_text' | 'file_topic'
        self.last_folder = None    # последняя созданная/открытая папка
        self.on_progress = None    # v6: живой статус длинных операций в чат
        self.on_timer = None       # v7: колбэк таймера (окно+звук), из GUI
        self.dispatch = {
            'help': self.cmd_help, 'greeting': self.cmd_greeting,
            'time': self.cmd_time, 'date': self.cmd_date, 'joke': self.cmd_joke,
            'thanks': self.cmd_thanks, 'who': self.cmd_who,
            'search': self.cmd_search, 'open_app': self.cmd_open,
            'open_folder': self.cmd_open_folder, 'weather': self.cmd_weather,
            'rates': self.cmd_rates, 'calc': self.cmd_calc,
            'timer': self.cmd_timer, 'translate': self.cmd_translate,
            'create_xlsx': self.cmd_xlsx,
            'find_file': self.cmd_find_file,
            'coin_dice': self.cmd_coin_dice,
            'create_folder': self.cmd_folder,
            'create_presentation': self.cmd_presentation,
            'create_file': self.cmd_file,
            'api_key': self.cmd_api_key,
            'note': self.cmd_note, 'system': self.cmd_system,
            'clear': self.cmd_clear, 'exit': self.cmd_exit,
            'language': self.cmd_language,
        }

    # ------------------------------------------------------------------ общее

    def _progress(self, text):
        """Живой статус в чат во время длинной работы (v6) — видно,
        что ассистент не завис, а делает что-то конкретное."""
        if self.on_progress:
            try:
                self.on_progress(text)
            except Exception:
                pass

    def handle(self, text):
        try:
            res = self._handle(text)
        except Exception as e:
            log('ОШИБКА handle: %r' % e)
            return [(_tr('Извините, произошла внутренняя ошибка: %s' % e),
                     'err')]
        # v7.1: перевод на язык интерфейса (повторный прогон в add_msg
        # идемпотентен — английские строки не содержат русских фрагментов)
        return [(_tr(m), k) for m, k in res]

    def _handle(self, text):
        raw = text.strip()
        if not raw:
            return [('Напишите команду. Список — «помощь».', 'meta')]

        # ждём ответ на уточняющий вопрос?
        if self.awaiting:
            if normalize(raw) in CANCEL_WORDS:
                self.awaiting = None
                return [('Хорошо, отменил.', 'text')]
            mode = self.awaiting
            self.awaiting = None
            if mode == 'pptx_topic':
                return self.cmd_presentation([], raw, forced_topic=raw)
            if mode == 'folder_name':
                return self.cmd_folder([], raw, forced_name=raw)
            if mode == 'note_text':
                return self.cmd_note([], raw, forced_text=raw)
            if mode == 'file_topic':
                return self.cmd_file([], raw, forced_text=raw)
            if mode == 'xlsx_topic':
                return self.cmd_xlsx([], raw, forced_topic=raw)
            if mode == 'api_key':
                if any(w in normalize(raw) for w in ('файл', 'прочитай', 'выбери')):
                    return [('__ASKFILE__', 'cmd')]
                return self._save_key(raw)

        # прислали сам ключ (например, вставили из буфера)?
        if re.match(r'^(AIza|AQ\.|aq\.)[A-Za-z0-9_\.\-]{16,}$', raw.strip()):
            return self._save_key(raw.strip())

        prs = _pairs(raw.split())
        nw = [n for _, n in prs]
        m = match_intent(nw)
        if m:
            score, _nlen, name, consumed = m
            consumed = set(consumed)
            arg = [prs[i][0] for i in range(len(prs)) if i not in consumed]
            log('КОМАНДА: %s (%.2f), аргумент: %r' % (name, score, ' '.join(arg)))
            return self.dispatch[name](arg, raw)

        # может, пользователь просто назвал приложение или сайт?
        rt = resolve_target(raw)
        if rt and rt[2] >= 0.8:
            log('КОМАНДА: прямое имя цели %r' % (rt[1],))
            return self._open_by_key(rt[0], rt[1], raw)

        # v5.1: формулировку не понял — пусть Gemini разберёт смысл фразы
        if gemini_key() and net_available():
            gi = gemini_intent(raw)
            if gi and gi[0] in self.dispatch:
                name, garg = gi
                log('РАСПОЗНАНО GEMINI: %s %r' % (name, garg))
                arg = [o for o, _ in _pairs(garg.split())]
                return self.dispatch[name](arg, garg or raw)

        return self._unknown(raw, nw)

    def _unknown(self, raw, nw):
        msgs = [('Не понял команду: «%s».' % raw, 'err')]
        best = (0.0, None)
        for it in INTENTS:
            # «пока» и «очисти» опасно предлагать наугад — пропускаем
            if it['name'] in ('exit', 'clear', 'api_key'):
                continue
            for ph in it['phrases']:
                for w in nw:
                    for pt in ph:
                        s = sim(w, pt)
                        if s > best[0]:
                            best = (s, it['example'])
        if best[1] and best[0] >= 0.65:
            ex = best[1]
            if LANG == 'en':
                ex = _EXAMPLE_EN.get(ex, ex)
            msgs.append(('Возможно, вы имели в виду «%s»?' % ex, 'text'))
        msgs.append(('Напишите «помощь» — покажу все команды.', 'meta'))
        return msgs

    # ------------------------------------------------------------- уточнения

    def _ask(self, question, hint):
        return [(question, 'text'), (hint, 'meta')]

    # ------------------------------------------------------------------ инфо

    def cmd_help(self, arg, raw):
        return [(HELP_TEXT_EN if LANG == 'en' else HELP_TEXT, 'text')]

    def cmd_greeting(self, arg, raw):
        return [(random.choice(GREETINGS_EN if LANG == 'en' else GREETINGS),
                 'text')]

    def cmd_time(self, arg, raw):
        now = datetime.datetime.now()
        return [('Сейчас %s, %s.' % (now.strftime('%H:%M'), WEEKDAYS[now.weekday()]),
                 'text')]

    def cmd_date(self, arg, raw):
        now = datetime.datetime.now()
        return [('Сегодня %s, %d %s %d года.' % (WEEKDAYS[now.weekday()], now.day,
                                                 MONTHS[now.month - 1], now.year),
                 'text')]

    def cmd_joke(self, arg, raw):
        return [(random.choice(JOKES_EN if LANG == 'en' else JOKES), 'text')]

    def cmd_thanks(self, arg, raw):
        return [(random.choice(THANKS_REPLIES_EN if LANG == 'en'
                               else THANKS_REPLIES), 'text')]

    def cmd_who(self, arg, raw):
        return [(WHO_TEXT_EN if LANG == 'en' else WHO_TEXT, 'text')]

    def cmd_system(self, arg, raw):
        lines = ['ХАРАКТЕРИСТИКИ КОМПЬЮТЕРА']
        lines.append('ОС:         %s %s' % (platform.system(), platform.release()))
        cpu = platform.processor() or platform.machine()
        lines.append('Процессор:  %s' % (cpu or 'не определён'))
        lines.append('Ядер:       %s' % os.cpu_count())
        ram = _ram_total_gb()
        if ram:
            lines.append('ОЗУ:        %s ГБ' % _fmt_gb(ram))
        try:
            rootp = os.path.abspath(os.sep)
            du = shutil.disk_usage(rootp)
            lines.append('Диск %s    всего %s ГБ, свободно %s ГБ'
                         % (rootp, _fmt_gb(du.total / 1024 ** 3),
                            _fmt_gb(du.free / 1024 ** 3)))
        except Exception:
            pass
        lines.append('Python:     %s' % platform.python_version())
        return [('\n'.join(lines), 'text')]

    def cmd_clear(self, arg, raw):
        return [('__CLEAR__', 'cmd')]

    def cmd_exit(self, arg, raw):
        return [('До встречи! Окно закроется через пару секунд.', 'text'),
                ('__EXIT__', 'cmd')]

    def cmd_language(self, arg, raw):
        """Переключатель языка интерфейса RU/EN (v7.1)."""
        # refresh=False: данные и файл меняем здесь (воркер-поток),
        # а интерфейс обновит poll() в главном потоке, увидев смену LANG.
        new = set_lang(' '.join(arg) if arg else raw, refresh=False)
        if new == 'en':
            return [('Язык переключен на английский.', 'ok'),
                    ('Language switched to English. Type "help" for commands.',
                     'text')]
        return [('Язык переключен на русский.', 'ok')]

    # ------------------------------------------------------------ интернет

    def cmd_search(self, arg, raw):
        q = ' '.join(arg).strip()
        if not q:
            return self._ask('Что найти? Напишите, например: «загугли погоду».',
                             'Отменить — «отмена».')
        url = 'https://www.google.com/search?q=' + urllib.parse.quote(q)
        msgs = [('Ищу в Google: «%s»...' % q, 'text')]
        try:
            ok = webbrowser.open(url)
        except Exception as e:
            log('Ошибка браузера: %r' % e)
            ok = False
        msgs.append(('Готово: поиск открыт в браузере.', 'ok') if ok
                    else ('Не удалось открыть браузер.', 'err'))
        return msgs

    def cmd_weather(self, arg, raw):
        """v7: погода прямо в чате (wttr.in + гео-поиск города)."""
        # город: «погода в москве», «погоду питера»
        city = None
        nt = normalize(raw)
        m = re.search(r'(?:погод\w*|температур\w*|за окном|на улице)\s*'
                      r'(?:в|во|для|по)?\s*(.+)$', nt)
        if m:
            cand = m.group(1).strip()
            cand = re.sub(r'^(?:в|во|для|по)\s+', '', cand)
            cand = re.sub(r'\s+(?:сейчас|сегодня|пожалуйста|пж)$', '', cand)
            if cand and len(cand) < 40:
                city = cand
        elif arg:
            city = ' '.join(arg).strip() or None
        if city:
            self._progress('Узнаю погоду для «%s»…' % city)
        else:
            self._progress('Узнаю погоду в вашем городе…')
        got = fetch_weather(city)
        if got is None and city and got != ('МЕСТО', city):
            pass
        if got and got != ('МЕСТО', city):
            lines, place = got
            title = 'ПОГОДА' + ((' · ' + place) if place else '')
            msgs = [('%s\n%s' % (title, '\n'.join(lines)), 'text'),
                    ('Источник: wttr.in и Open-Meteo (без ключей). '
                     'Подробнее: «открой погоду» — сайт с графиками.',
                     'meta')]
            return msgs
        # не смогли в чат — честно открываем сайт
        if city:
            url = 'https://wttr.in/%s?lang=ru' % urllib.parse.quote(city)
        else:
            url = SITES['погода']
        msgs = [('Не получилось собрать погоду в чат — открываю сайт…', 'text')]
        try:
            ok = webbrowser.open(url)
        except Exception:
            ok = False
        msgs.append(('Готово: погода открыта в браузере.', 'ok') if ok
                    else ('Не удалось открыть браузер и погоду.', 'err'))
        return msgs

    def cmd_rates(self, arg, raw):
        """v7: курсы валют ЦБ РФ прямо в чате."""
        nt = normalize(raw)
        want = None
        for cur, names in (('USD', ('доллар', 'доллара', 'бакс')),
                           ('EUR', ('евро',)),
                           ('CNY', ('юань', 'юаня')),
                           ('GBP', ('фунт',)),
                           ('AED', ('дирхам',)),
                           ('TRY', ('лира', 'лиры')),
                           ('KZT', ('тенге',)),
                           ('JPY', ('иена', 'йена'))):
            if any(n in nt for n in names):
                want = cur
                break
        self._progress('Беру свежие курсы ЦБ РФ…')
        got = fetch_rates()
        if not got:
            msgs = [('Курсы сейчас недоступны (нет сети или ЦБ молчит).',
                     'err')]
            try:
                okk = webbrowser.open('https://www.cbr.ru/currency_base/'
                                      'daily/')
                if okk:
                    msgs.append(('Открыл сайт ЦБ с таблицей курсов.', 'text'))
            except Exception:
                pass
            return msgs
        lines, date_str = got
        if want and len(lines) > 1:
            one = [l for l in lines if l.split(':')[0] in
                   ('Доллар США', 'Евро', 'Юань', 'Фунт стерлингов',
                    'Дирхам ОАЭ', 'Турецкая лира', 'Тенге', 'Иена')]
            # показываем запрошенную валюту первой, потом остальные
            head = {'USD': 'Доллар США', 'EUR': 'Евро', 'CNY': 'Юань',
                    'GBP': 'Фунт стерлингов', 'AED': 'Дирхам ОАЭ',
                    'TRY': 'Турецкая лира', 'KZT': 'Тенге', 'JPY': 'Иена'}
            target = head.get(want)
            first = [l for l in one if l.startswith(target)]
            rest = [l for l in one if not l.startswith(target)]
            lines = first + rest
        body = 'КУРСЫ ЦБ РФ · %s\n%s' % (date_str, '\n'.join(lines))
        return [(body, 'text'),
                ('Кэш 10 минут — «курс» обновит при необходимости. '
                 'Все валюты: cbr-xml-daily.ru', 'meta')]

    def cmd_calc(self, arg, raw):
        """v7: калькулятор в чате («посчитай 2+2*10», «15% от 200»)."""
        # ВАЖНО: выражение берём из RAW: нормализация удаляет +, *, % и
        # запятые-десятичные — arg для математики бесполезен
        expr = raw.strip()
        expr = re.sub(r'^\s*(?:посчитай|вычисли|посчитать|вычислить|'
                      r'сколько\s+будет|сколько\s+получится|чему\s+равно|'
                      r'calculate|compute|evaluate|'
                      r'how\s+much\s+is|what\s+is)'
                      r'\s*:?\s*', '', expr, flags=re.IGNORECASE)
        expr = expr.rstrip('?!. ').strip()
        if not expr or not re.search(r'\d', expr):
            return self._ask('Что посчитать? Напишите пример.',
                             'Например: «посчитай 2+2*10», «сколько будет '
                             '15% от 200». Отменить — «отмена».')
        res = calc_expr(expr)
        if res:
            val, pretty = res
            return [(pretty, 'text')]
        # проценты могли быть «X% от Y» — но без «от» непонятно
        if '%' in expr and ' от ' not in expr.lower():
            return [('Понял проценты, но нужно «от чего»: напишите '
                     'например «15% от 200».', 'text')]
        return [('Не смог вычислить «%s».' % expr, 'err'),
                ('Понимаю: + - * / ^ (степень), % (остаток), скобки, '
                 'запятую-десятичную и «15% от 200».', 'meta')]

    def cmd_timer(self, arg, raw):
        """v7: таймер/напоминание. По срабатыванию — пузырь + окно + звук."""
        secs = parse_duration(raw)
        if not secs and arg:
            secs = parse_duration(' '.join(arg))
        if not secs:
            return self._ask('На сколько поставить таймер?',
                             'Например: «таймер на 5 минут», «напомни через '
                             '30 секунд». Отменить — «отмена».')
        if self.on_timer is None:
            return [('Внутренняя проблема: таймер недоступен в этом режиме.',
                     'err')]
        label = _human_secs(secs)
        self.on_timer(secs, raw.strip()[:80])
        return [('Таймер запущен: %s. Напомню в чате, окном и звуком.' % label,
                 'ok'),
                ('Продолжаю слушать ваши команды — таймер идёт в фоне.',
                 'meta')]

    def cmd_translate(self, arg, raw):
        """v7: перевод. Gemini (если есть ключ) или Google Переводчик."""
        text = ' '.join(arg).strip()
        nt = normalize(raw)
        m = re.search(r'перевед(?:и|ите)\s+(.+)$', nt)
        if m:
            text = m.group(1)
        text = re.sub(r'^(?:на русский|на английский|с русского|'
                       r'с английского)\s+', '', text).strip()
        text = re.sub(r'\s+(?:на русский|на английский|с русского|'
                      r'с английского)$', '', text).strip()
        if not text:
            return self._ask('Что перевести? Напишите текст.',
                             'Например: «переведи hello world». '
                             'Отменить — «отмена».')
        # Gemini-перевод без ключа невозможен — сразу сайт
        if gemini_key() and net_available():
            self._progress('Перевожу через Gemini…')
            translated = gemini_translate(text)
            if translated:
                return [('ПЕРЕВОД\n%s' % translated, 'text')]
        url = ('https://translate.google.com/?sl=auto&tl=ru&text='
               + urllib.parse.quote(text) + '&op=translate')
        try:
            ok = webbrowser.open(url)
        except Exception:
            ok = False
        if ok:
            return [('Открыл Google Переводчик с этим текстом.', 'ok')]
        return [('Не удалось открыть переводчик.', 'err')]

    def cmd_coin_dice(self, arg, raw):
        nt = normalize(raw)
        if 'кубик' in nt or 'кост' in nt:
            n = random.randint(1, 6)
            return [('🎲 Кубик: %d' % n, 'text')]
        if 'число' in nt:
            m = re.search(r'от\s+(\d+)\s+до\s+(\d+)', nt)
            lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, 100)
            if lo > hi:
                lo, hi = hi, lo
            return [('Случайное число: %d (из %d–%d)'
                     % (random.randint(lo, hi), lo, hi), 'text')]
        side = random.choice(('ОРЁЛ', 'РЕШКА'))
        return [('🪙  %s' % side, 'text')]

    def cmd_find_file(self, arg, raw):
        """v7: поиск файлов по столу/документам/загрузкам (+открытие)."""
        nt = normalize(raw)
        open_it = bool(re.match(r'^(открой|открывай|запусти)\b', nt))
        name = ' '.join(arg).strip()
        name = re.sub(r'^(файл|документ|презентацию|презентация|таблицу|'
                      r'таблица)\s+', '', normalize(name)).strip()
        name = re.sub(r'^(презентацию|презентация)\b', '', name).strip()
        if not name:
            return self._ask('Какой файл найти? Напишите имя.',
                             'Например: «найди файл отчет». '
                             'Отменить — «отмена».')
        self._progress('Ищу «%s» на столе, в документах и загрузках…' % name)
        hits = search_files(name, limit=6)
        if not hits:
            return [('Файлов с «%s» не нашёл (искал на рабочем столе, '
                     'в документах и загрузках, глубина 2).' % name, 'err'),
                    ('Подсказка: скажите точнее имя или попросите '
                     '«создай презентацию про …» — я сделаю файл сам.',
                     'meta')]
        lines = ['Нашёл %d:' % len(hits)]
        for i, (p, _) in enumerate(hits, 1):
            base = os.path.basename(p)
            folder = os.path.dirname(p)
            short = os.path.basename(folder) or folder
            stamp = ''
            try:
                stamp = datetime.datetime.fromtimestamp(
                    os.path.getmtime(p)).strftime('%d.%m.%Y')
            except Exception:
                pass
            lines.append('%d. %s   (папка «%s», %s)' % (i, base, short, stamp))
        msgs = [('\n'.join(lines), 'text')]
        if open_it:
            p = hits[0][0]
            try:
                os.startfile(p)
                msgs.append(('Открываю: %s' % os.path.basename(p), 'ok'))
            except Exception as e:
                msgs.append(('Не удалось открыть: %s' % e, 'err'))
        else:
            msgs.append(('Открыть первый — «открой файл %s».'
                         % os.path.splitext(os.path.basename(hits[0][0]))[0],
                         'meta'))
        return msgs

    def cmd_xlsx(self, arg, raw, forced_topic=None):
        """v7: «создай таблицу про X» -> настоящий .xlsx с оформлением."""
        if forced_topic:
            topic = forced_topic.strip().strip(' «»"\'')
            loc = None
        else:
            loc, rest = extract_location(_pairs(arg))
            rest = _strip_filler(rest)
            rest = [(o, n) for o, n in rest if n not in
                    ('таблицу', 'таблица', 'таблицы', 'excel', 'xlsx',
                     'эксель', 'ексель')]
            topic = ' '.join(o for o, _ in strip_topic_prefix(rest)).strip(' «»"\'')
        topic = re.sub(r'^(создай|сделай|сгенерируй|подготовь|собери|'
                       r'составь)\s+', '', topic, flags=re.IGNORECASE).strip()
        topic = re.sub(r'^(про|о|об|на тему|по теме)\s+', '', topic,
                       flags=re.IGNORECASE).strip()
        topic = nominative(topic)
        if not topic:
            self.awaiting = 'xlsx_topic'
            return self._ask('Про что сделать таблицу? Напишите тему.',
                             'Например: «создай таблицу про космос». '
                             'Отменить — «отмена».')
        folder = self._resolve_dest(loc)
        fname = safe_filename(topic, default='Таблица') + '.xlsx'
        path = unique_path(os.path.join(folder, fname))
        log('Создаю таблицу: тема=%r, файл=%r' % (topic, path))
        try:
            self._progress('Собираю содержание и пишу таблицу…')
            header, rows = xlsx_content_for(topic)
            x = MiniXLSX(sheet_title=safe_filename(topic, 'Таблица')[:28])
            x.add_row(header, header=True)
            for r in rows:
                x.add_row(r)
            x.set_width(0, 22)
            x.set_width(1, 46)
            x.set_width(2, 46)
            x.set_width(3, 26)
            x.save(path)
        except Exception as e:
            log('ОШИБКА создания xlsx: %r' % e)
            return [('Не удалось создать таблицу: %s' % e, 'err'),
                    ('Файл НЕ создан — это честный отчёт об ошибке.', 'meta')]
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        if not os.path.isfile(path) or size < 1000 \
                or not zipfile.is_zipfile(path):
            return [('Файл не записался на диск — таблица НЕ создана.', 'err')]
        self.last_folder = folder
        return [
            ('Готово! Таблица создана и проверена на диске.', 'ok'),
            ('Файл: %s' % path, 'text'),
            ('Тема: «%s» · Строк: %d · Размер: %d КБ'
             % (topic, len(rows), size // 1024), 'text'),
            ('В таблице: шапка с заливкой и закреплена, автофильтр, '
             'ширины колонок под текст.', 'meta'),
            ('Открой файл — Excel (или LibreOffice) покажет всё сразу.',
             'meta'),
        ]

    # ------------------------------------------------------------ открытие

    def _suggest_targets(self, raw):
        nw = normalize(raw).split()
        scored = []
        for table in (SITES, APPS):
            for key in table:
                kw = key.split()
                s = 0.0
                for w in nw:
                    for kt in kw:
                        s = max(s, sim(w, kt))
                scored.append((s, key))
        scored.sort(reverse=True)
        seen = []
        for s, k in scored:
            if s >= 0.5 and k not in seen:
                seen.append(k)
            if len(seen) >= 3:
                break
        return seen

    def _open_by_key(self, kind, key, raw):
        if kind == 'url':
            url = key
            label = key
        elif kind == 'site':
            url = SITES[key]
            label = key
        else:
            app_kind, target = APPS[key]
            if app_kind == 'site':
                url = target
                label = key
            else:
                return self._launch_exe(key, target)
        msgs = [('Открываю в браузере: %s...' % label, 'text')]
        try:
            ok = webbrowser.open(url)
        except Exception:
            ok = False
        msgs.append(('Готово: открыл в браузере.', 'ok') if ok
                    else ('Не удалось открыть браузер.', 'err'))
        return msgs

    def _launch_exe(self, key, target):
        msgs = [('Запускаю: %s...' % key, 'text')]
        if os.name != 'nt':
            msgs.append(('Запуск программ доступен только на Windows.', 'err'))
            return msgs
        try:
            os.startfile(target)
            msgs.append(('Готово: запустил.', 'ok'))
        except Exception as e:
            log('Не удалось запустить %r: %r' % (target, e))
            msgs.append(('Не удалось запустить «%s» (%s).' % (key, e), 'err'))
        return msgs

    def cmd_open(self, arg, raw):
        target_raw = ' '.join(arg).strip()
        if not target_raw:
            return self._ask('Что открыть?',
                             'Например: «открой блокнот», «открой роблокс», «открой ютуб».')
        # v5.1: точное совпадение с ярлыком меню «Пуск» важнее словаря —
        # «открой роблокс» запустит установленную игру, а не сайт
        if os.name == 'nt':
            strong = _search_shortcut(target_raw, strong_only=True)
            if strong:
                return self._launch_shortcut(strong[0])
        rt = resolve_target(target_raw)
        if rt:
            return self._open_by_key(rt[0], rt[1], target_raw)
        # v5.1: незнакомое имя — ищем установленную программу нечётко
        if os.name == 'nt':
            hits = _search_shortcut(target_raw)
            if hits:
                return self._launch_shortcut(hits[0])
        msgs = [('Не нашёл на этом компьютере приложение или сайт «%s».' % target_raw,
                 'err')]
        sugg = self._suggest_targets(target_raw)
        if sugg:
            msgs.append(('Ближайшие из известных: %s.' % ', '.join(sugg), 'text'))
        msgs.append(('Подсказка: установленную программу можно назвать как '
                     'в меню «Пуск» — я умею её искать. Известные мне: %s.' %
                     ', '.join(sorted(list(SITES) + list(APPS))[:24]), 'meta'))
        return msgs

    def _launch_shortcut(self, hit):
        """Запускает найденный ярлык/exe. hit = (имя, путь, совпадение)."""
        name, path, _sc = hit
        msgs = [('Нашёл программу «%s» в меню «Пуск» — запускаю...' % name,
                 'text')]
        try:
            os.startfile(path)
            msgs.append(('Готово: запустил.', 'ok'))
        except Exception as e:
            log('Не удалось запустить %r: %r' % (path, e))
            msgs.append(('Не удалось запустить «%s» (%s).' % (name, e), 'err'))
        return msgs

    def cmd_open_folder(self, arg, raw):
        name = ' '.join(arg).strip()
        cands = []
        if name:
            if os.path.isabs(name):
                cands.append(name)
            for base in (desktop_dir(), documents_dir(), os.path.expanduser('~')):
                cands.append(os.path.join(base, name))
        else:
            cands.append(self.last_folder or desktop_dir())
        for c in cands:
            if c and os.path.isdir(c):
                self.last_folder = c
                if os.name == 'nt':
                    try:
                        os.startfile(c)
                        return [('Открываю папку: %s' % c, 'text'),
                                ('Готово: папка открыта в Проводнике.', 'ok')]
                    except Exception as e:
                        return [('Не удалось открыть папку: %s' % e, 'err')]
                try:
                    subprocess.Popen(['xdg-open', c])
                    return [('Открываю папку: %s' % c, 'text'),
                            ('Готово: папка открыта.', 'ok')]
                except Exception as e:
                    return [('Не удалось открыть папку: %s' % e, 'err')]
        return [('Не нашёл папку «%s». Проверьте имя.' % name, 'err')]

    # --------------------------------------------------------------- файлы

    def _folder_candidates(self, name):
        """Все существующие папки с таким именем (глубина до 1 уровня).

        Ищем на рабочем столе, в документах, загрузках и домашней папке,
        плюс внутри их подпапок — чтобы не создавать дубликат на рабочем
        столе, когда папка давно лежит, например, в документах."""
        home = os.path.expanduser('~')
        bases = [desktop_dir(), documents_dir(),
                 os.path.join(home, 'Downloads'),
                 os.path.join(home, 'Загрузки'), home]
        cands = []
        if os.path.isabs(name):
            cands.append(name)
        for base in bases:
            if not base:
                continue
            cands.append(os.path.join(base, name))
            try:
                for sub in os.listdir(base):
                    cands.append(os.path.join(base, sub, name))
            except Exception:
                pass
        seen, out = set(), []
        for c in cands:
            try:
                c = os.path.normpath(c)
            except Exception:
                continue
            if c not in seen and os.path.isdir(c):
                seen.add(c)
                out.append(c)
        return out

    def _resolve_dest(self, loc):
        """Куда сохранять: путь или None (тогда рабочий стол)."""
        if loc is None:
            return desktop_dir()
        kind = loc[0]
        if kind == 'desktop':
            return desktop_dir()
        if kind == 'documents':
            return documents_dir()
        if kind == 'last':
            return self.last_folder or desktop_dir()
        if kind == 'folder':
            name = loc[1]
            cands = self._folder_candidates(name)
            if cands:
                return cands[0]
            p = os.path.join(desktop_dir(), name)
            try:
                os.makedirs(p, exist_ok=True)
                return p
            except Exception as e:
                log('Не удалось создать папку %r: %r' % (p, e))
                return desktop_dir()
        return desktop_dir()

    def cmd_folder(self, arg, raw, forced_name=None):
        if forced_name:
            name = forced_name.strip().strip(' «»"\'')
            loc = None
        else:
            loc, rest = extract_location(_pairs(arg))
            rest = _strip_filler(rest)
            name = ' '.join(o for o, _ in rest).strip().strip(' «»"\'')
        if not name:
            self.awaiting = 'folder_name'
            return self._ask('Как назвать папку? Напишите имя.',
                             'Например: «мои работы». Отменить — «отмена».')
        if re.search(r'[\\/:*?"<>|]', name):
            return [('В имени папки нельзя использовать символы: \\ / : * ? " < > |',
                     'err')]
        base = self._resolve_dest(loc)
        path = os.path.join(base, name)
        if os.path.isdir(path):
            self.last_folder = path
            return [('Папка уже существует: %s' % path, 'text')]
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            log('Ошибка создания папки: %r' % e)
            return [('Не удалось создать папку: %s' % e, 'err')]
        if os.path.isdir(path):
            self.last_folder = path
            return [('Готово! Папка создана: %s' % path, 'ok')]
        return [('Не удалось создать папку. Проверьте имя и права доступа.', 'err')]

    def cmd_presentation(self, arg, raw, forced_topic=None):
        n_req = parse_slide_count(raw)
        n_slides = 8 if not n_req else max(5, min(12, n_req))
        if forced_topic:
            topic = forced_topic.strip().strip(' «»"\'')
            # «про космос» -> «космос»
            topic = re.sub(r'^(про|о|об|на тему|по теме)\s+', '',
                           topic, flags=re.IGNORECASE).strip()
            loc = None
        else:
            loc, rest = extract_location(_pairs(arg))
            rest = _strip_filler(rest)
            topic = ' '.join(o for o, _ in strip_topic_prefix(rest)).strip().strip(' «»"\'')
        # страховка: убрать случайно уцелевшие слова команды из темы
        topic = re.sub(r'^(создай|сделай|сгенерируй|подготовь|собери|'
                       r'презентацию|презентация|слайды)\s+',
                       '', topic, flags=re.IGNORECASE).strip()
        # «на 10 слайдов» не должно попадать в название темы
        topic = re.sub(r'\s*(?:на|из|в)?\s*\d{1,2}\s*(?:слайд\w*|страниц\w*)\s*$',
                       '', topic).strip()
        topic = re.sub(r'\s*(?:на|из|в)\s+(?:пять|шесть|семь|восемь|девять|'
                       r'десять|одиннадцать|двенадцать)\s+'
                       r'(?:слайд\w*|страниц\w*)\s*$', '', topic).strip()
        topic = nominative(topic)
        if not topic:
            self.awaiting = 'pptx_topic'
            return self._ask('На какую тему сделать презентацию? Напишите тему.',
                             'Например: «про космос» или «искусственный интеллект». '
                             'Можно добавить «на 10 слайдов». Отменить — «отмена».')
        folder = self._resolve_dest(loc)
        fname = safe_filename(topic) + '.pptx'
        path = unique_path(os.path.join(folder, fname))
        log('Создаю презентацию: тема=%r, файл=%r, слайдов=%d'
            % (topic, path, n_slides))
        try:
            self._progress('Пишу текст и структуру слайдов…')
            photos = {}
            used = _SyncExclude()   # занятые адреса фото: без близнецов
            n_sec = max(3, min(n_slides - 2, 10))
            pre_pool = None
            # v6: фото русской Википедии и точное название статьи качаются
            # ПАРАЛЛЕЛЬНО генерации текста — не ждём Gemini, чтобы начать
            if net_available():
                try:
                    pre_pool = ThreadPoolExecutor(max_workers=2)
                    fut_wikiru = pre_pool.submit(fetch_wiki_photos, topic,
                                                 n_sec + 1)
                    fut_title = pre_pool.submit(wiki_resolve_title, topic)
                except Exception:
                    pre_pool = None
            content = content_for(topic, n_slides)
            # v6: большие презентации — до 10 разделов («на 12 слайдов»
            # больше не обрезается до 6)
            n_sec = max(3, min(n_slides - 2, len(content['sections']), 10))
            sec_titles = [str(s[0]) for s in content['sections'][:n_sec]]

            if pre_pool is not None:
                self._progress('Текст готов — ищу фото в 5 источниках '
                               'параллельно…')
                # фото-запросы: v6 берёт их из ТОГО ЖЕ ответа Gemini, что и
                # текст (минус отдельный запрос); запасной случай — текст
                # дала не Gemini, а ключ живой: тогда один отдельный вызов
                pq = content.get('pq') or {}
                if not pq and not content.get('source', '').startswith('Google') \
                        and gemini_key():
                    try:
                        pq = photo_queries(topic, sec_titles)
                    except Exception:
                        pq = {}
                topic_en = [str(q) for q in (pq.get('topic') or [])
                            if str(q).strip()][:2]
                # точное название статьи Википедии по теме (v5.2.2):
                # «ии» -> «Искусственный интеллект», а не «Иисус Христос»
                try:
                    topic_wiki = fut_title.result() or topic
                except Exception:
                    topic_wiki = topic

                def _search(q):
                    """Одно фото по запросу из трёх источников -> bytes|None.

                    ВАЖНО: fetch_commons_photos возвращает СПИСОК байтов —
                    берём первый элемент; дальше Openverse и Flickr отдают
                    уже байты."""
                    got = fetch_commons_photos(q, want=1, exclude=used)
                    if got:
                        return got[0]
                    return (fetch_openverse_photo(q, exclude=used)
                            or fetch_flickr_photo(q, exclude=used))

                # мягкий бюджет времени на весь фото-этап (v6: 45 секунд
                # вместо 100 — при медленной сети презентация всё равно
                # соберётся, а не будет «молчать»)
                deadline = time.time() + 45

                # 1) фото русской Википедии (качались параллельно с текстом)
                try:
                    imgs = fut_wikiru.result()
                except Exception:
                    imgs = []
                if imgs:
                    photos[-1] = imgs[0]
                    for i in range(min(n_sec, len(imgs) - 1)):
                        photos[i] = imgs[i + 1]

                # 2) ВСЁ ОСТАЛЬНОЕ — ПАРАЛЛЕЛЬНО (v6): каждый пустой раздел
                #    ищет фото одновременно с другими; рядом отдельные
                #    задачи — английская Википедия и титульное фото.
                #    Раньше это была ОДНА цепочка на раздел ПОДРЯД.
                missing = [i for i in range(n_sec) if i not in photos]
                with ThreadPoolExecutor(max_workers=n_sec + 2) as pool:
                    futs = {}

                    def _sec_job(i):
                        words = re.findall(r'[а-яa-zе]{4,}',
                                           normalize(sec_titles[i]))[:2]
                        own = (topic_wiki + ' ' + ' '.join(words)).strip()
                        # английские запросы — раньше русских (v5.2.2):
                        # Commons, Openverse и Flickr описывают фото
                        # по-английски
                        qs = ([str(q) for q in (pq.get('sections') or {})
                               .get(str(i), [])]
                              + topic_en + [own, topic_wiki])[:3]
                        for q in qs:
                            if time.time() > deadline:
                                return None
                            ph = _search(q)
                            if ph:
                                return (i, ph)
                        return None

                    for i in missing:
                        futs[pool.submit(_sec_job, i)] = i

                    fut_en = None
                    if topic_en and (missing or -1 not in photos):
                        fut_en = pool.submit(
                            fetch_wiki_photos, topic_en[0],
                            want=len(missing) + (0 if -1 in photos else 1),
                            lang='en')

                    def _title_job():
                        for q in (topic_en + [topic_wiki])[:2]:
                            if time.time() > deadline:
                                return None
                            ph = _search(q)
                            if ph:
                                return (-1, ph)
                        return None

                    if -1 not in photos:
                        futs[pool.submit(_title_job)] = -1

                    for fut in list(futs):
                        try:
                            r = fut.result()
                        except Exception:
                            r = None
                        if r:
                            i, ph = r
                            if i not in photos:
                                photos[i] = ph

                    # английская Википедия добирает всё, что ещё пусто
                    if fut_en is not None:
                        try:
                            en_imgs = fut_en.result()
                        except Exception:
                            en_imgs = []
                        if en_imgs:
                            if -1 not in photos:
                                photos[-1] = en_imgs[0]
                                en_imgs = en_imgs[1:]
                            for i in range(n_sec):
                                if not en_imgs:
                                    break
                                if i not in photos:
                                    photos[i] = en_imgs.pop(0)
                # без генерации (v5.2): если фото не нашлось — раздел
                # останется с генеративным артом; честно скажем об этом
                pre_pool.shutdown(wait=False)
            self._progress('Собираю слайды и записываю файл…')
            n_sl, source, n_pics, n_photos = build_presentation(
                topic, path, n_slides, content, photos)
        except Exception as e:
            log('ОШИБКА создания pptx: %r' % e)
            return [('Не удалось создать презентацию: %s' % e, 'err'),
                    ('Файл НЕ создан — это честный отчёт об ошибке, '
                     'а не выдуманный успех.', 'meta')]
        # ЧЕСТНАЯ проверка результата
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        if not os.path.isfile(path) or size < 5000 or not zipfile.is_zipfile(path):
            return [('Файл не записался на диск — презентация НЕ создана.', 'err')]
        self.last_folder = folder
        if n_req and n_req != n_sl:
            note = ('Просили %d слайдов — вышло %d (беру не больше 6 разделов).'
                    % (n_req, n_sl), 'meta')
        else:
            note = ('Открой файл и дополни под свою задачу — основа уже готова.',
                    'meta')
        # КАРТИНКИ — честный расклад (v5.2): только настоящие фото
        # из источников или генеративный арт (без AI-генерации фото)
        n_real = sum(1 for v in photos.values()
                     if v and v[:2] == b'\xff\xd8')
        n_art = max(0, n_pics - n_real)
        if n_real:
            where = 'Википедия, Wikimedia Commons, Openverse, Flickr'
            if n_real == n_pics:
                img_note = ('Картинки: %d настоящих фото по теме (%s).'
                            % (n_real, where))
            else:
                img_note = ('Картинки: %d настоящих фото по теме (%s) '
                            'и %d разделов без фото (там декоративный фон).'
                            % (n_real, where, n_art))
        else:
            img_note = ('Картинки: %d декоративных фонов — настоящие '
                        'фото в открытых источниках не нашлись или нет сети.'
                        % n_art)
        msgs = [
            ('Готово! Презентация создана и проверена на диске.', 'ok'),
            ('Файл: %s' % path, 'text'),
            ('Тема: «%s» · Слайдов: %d · Размер: %d КБ'
             % (topic, n_sl, size // 1024), 'text'),
            ('Текст: %s' % source, 'meta'),
            (img_note, 'meta'),
            note,
            ('Открыть папку с файлом: «открой папку».', 'meta'),
        ]
        if content.get('gemini_warn'):
            msgs.append(('Gemini не сработал: %s. Подстраховался другим '
                         'источником — см. строку «Текст». Проверить ключ: '
                         '«подключи гугл».' % content['gemini_warn'], 'meta'))
        return msgs

    # ------------------------------------------- текстовые документы

    def cmd_file(self, arg, raw, forced_text=None):
        """«создай текстовый документ про X» -> .txt;
        «создай документ/ворд про X» -> настоящий .docx."""
        nt = normalize(raw)
        want_docx = bool(re.search(r'\b(ворд|word|docx|doc)\b', nt))
        if forced_text is not None:
            topic = forced_text.strip().strip(' «»"\'')
            loc = None
        else:
            loc, rest = extract_location(_pairs(arg))
            rest = _strip_filler(rest)
            rest = [(o, n) for o, n in rest if n not in _FILE_WORDS]
            topic = ' '.join(o for o, _ in strip_topic_prefix(rest)).strip(' «»"\'')
        # страховка: убрать случайно уцелевшие слова команды из темы
        topic = re.sub(r'^(создай|сделай|сгенерируй|подготовь|набери|напиши|'
                       r'составь|пожалуйста)\s+',
                       '', topic, flags=re.IGNORECASE).strip()
        topic = re.sub(r'^(про|о|об|на тему|по теме)\s+', '', topic,
                       flags=re.IGNORECASE).strip()
        topic = nominative(topic)
        if not topic:
            self.awaiting = 'file_topic'
            return self._ask('О чём написать документ? Напишите тему.',
                             'Например: «про искусственный интеллект». '
                             'Отменить — «отмена».')
        folder = self._resolve_dest(loc)
        try:
            content = content_for(topic, 8)
        except Exception as e:
            log('ОШИБКА контента для документа: %r' % e)
            content = _norm_content(generic_content(topic, 5))
        ext = '.docx' if want_docx else '.txt'
        fname = safe_filename(topic, default='Документ') + ext
        path = unique_path(os.path.join(folder, fname))
        log('Создаю документ: тема=%r, файл=%r, формат=%s'
            % (topic, path, ext))
        try:
            if want_docx:
                _write_docx(content, path, topic)
            else:
                _write_txt(content, path)
        except Exception as e:
            log('ОШИБКА создания документа: %r' % e)
            return [('Не удалось создать документ: %s' % e, 'err'),
                    ('Файл НЕ создан — это честный отчёт об ошибке.', 'meta')]
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        ok = size > 100 and (not want_docx or zipfile.is_zipfile(path))
        if not ok:
            return [('Файл не записался на диск — документ НЕ создан.', 'err')]
        self.last_folder = folder
        return [
            ('Готово! Документ создан и проверен на диске.', 'ok'),
            ('Файл: %s' % path, 'text'),
            ('Тема: «%s» · Формат: %s · Размер: %d КБ'
             % (topic, 'DOCX' if want_docx else 'TXT', size // 1024), 'text'),
            ('Текст: %s' % content['source'], 'meta'),
            ('Открой файл — основа уже готова, дополняйте под себя.', 'meta'),
        ]

    # ------------------------------------------------- подключение Gemini API

    def cmd_api_key(self, arg, raw):
        nt = normalize(raw)
        if ('удали' in nt or 'забудь' in nt or 'отключи' in nt) and 'ключ' in nt:
            try:
                os.remove(os.path.join(_script_dir(), GEMINI_KEY_FILE))
                return [('Ключ удалён. Текст для презентаций беру из Википедии '
                         'и встроенной базы знаний.', 'ok')]
            except Exception:
                return [('Ключа и так нет — использую Википедию и встроенную базу.',
                         'text')]
        if any(w in nt for w in ('файл', 'прочитай', 'выбери', 'импорт')):
            # Ключ вводится выбором файла — копировать ничего не нужно.
            # Сами файлы открывает главный поток (окно), поэтому — служебная
            # команда '__ASKFILE__', её обработает poll() в GUI.
            return [('__ASKFILE__', 'cmd')]
        cand = [w for w in (arg or []) if len(w) >= 16]
        if not cand and len(raw.strip()) >= 16 and ' ' not in raw.strip():
            cand = [raw.strip()]
        if cand:
            return self._save_key(cand[0])
        if gemini_key():
            return [('Ключ Gemini уже подключён (%s…).' % gemini_key()[:4], 'text'),
                    ('Чтобы заменить: вставьте новый ключ (Ctrl+V или правая '
                     'кнопка мыши → «Вставить») и отправьте; или напишите '
                     '«ключ из файла» и выберите txt-файл с ключом. '
                     'Удалить — «удали ключ».', 'meta')]
        self.awaiting = 'api_key'
        return self._ask('Пришлите API-ключ Gemini одним сообщением '
                         '(можно вставить: Ctrl+V или правая кнопка мыши '
                         '→ «Вставить»; или напишите «ключ из файла»).',
                         'Бесплатный ключ: aistudio.google.com → «Get API key» '
                         '(начинается с AIza или AQ.). Отменить — «отмена».')

    def _save_key(self, key):
        key = key.strip().strip(' «»"\'')
        try:
            save_gemini_key(key)
        except Exception as e:
            return [('Не получилось сохранить ключ: %s' % e, 'err')]
        msgs = [('Ключ сохранён в gemini_key.txt рядом с программой — '
                 'он не уходит с компьютера.', 'ok'),
                ('Теперь текст презентаций пишет Google Gemini. '
                 'Проверьте: «сделай презентацию про космос».', 'text')]
        if not (key.startswith('AIza') or key.startswith('AQ.')):
            msgs.append(('Внимание: ключи Gemini начинаются с «AIza…» или «AQ.…». '
                         'Если генерация не заработает — проверьте ключ в '
                         'aistudio.google.com; я подстрахуюсь Википедией.', 'meta'))
        return msgs

    def cmd_note(self, arg, raw, forced_text=None):
        note = (forced_text or ' '.join(arg)).strip()
        if not note:
            self.awaiting = 'note_text'
            return self._ask('Что записать в заметку? Напишите текст.',
                             'Отменить — «отмена».')
        stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        path = os.path.join(desktop_dir(), 'Заметка_%s.txt' % stamp)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('Заметка · %s\n%s\n\n%s\n'
                        % (datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
                           '-' * 30, note))
        except Exception as e:
            return [('Не удалось сохранить заметку: %s' % e, 'err')]
        if os.path.isfile(path):
            return [('Готово! Заметка сохранена: %s' % path, 'ok')]
        return [('Заметка не записалась на диск.', 'err')]


# ----------------------------------------------------------------------------
# Графический интерфейс (tkinter, тёмная тема)
# ----------------------------------------------------------------------------

def _ui_font_family():
    """Шрифт интерфейса с гарантированной кириллицей.

    Windows — родной Segoe UI; Linux/macOS — первый доступный из
    системных (у всех есть кириллица). Без этого Tk мог выбрать
    подстановку без русских глифов — текст «исчезал»."""
    try:
        import tkinter.font as _f
        fams = set(_f.families())
        for fam in ('Segoe UI', 'SF Pro Text', 'Ubuntu', 'Roboto',
                    'DejaVu Sans', 'Verdana', 'Arial'):
            if fam in fams:
                return fam
    except Exception:
        pass
    return 'Segoe UI'


def _apply_app_icon(root):
    """v7: значок приложения — ICO рядом с программой + Tk photo.

    Windows показывает его в панели задач и заголовке; генерируем
    вручную (PNG в ICO-контейнере), без библиотек. Ошибка — не беда:
    окно просто останется со стандартной иконкой."""
    try:
        path = os.path.join(_script_dir(), 'rotogo_icon.ico')
        need = True
        try:
            need = os.path.getsize(path) < 100
        except Exception:
            need = True
        if need and not _write_icon_ico(path):
            return
        if os.name == 'nt':
            try:
                root.iconbitmap(path)
                return
            except Exception:
                pass
        # не-Windows: показываем большой PNG рядом с заголовком
        try:
            import base64 as _b64
            c = PNGCanvas(32, 32, bg=(43, 26, 99))
            c.frame(1, 1, 30, 30, (167, 139, 250), t=2)
            root.tk.call('image', 'create', 'photo', 'rb_icon',
                        '-data', _b64.b64encode(c.png()))
            root.iconphoto(True, root.tk.call('image', 'create', 'photo',
                                              'rb_icon'))
        except Exception:
            pass
    except Exception as e:
        log('Иконка не поставилась: %r' % e)


def _write_icon_ico(path):
    """Собирает .ico вручную (PNG в ICO-контейнере, 5 размеров).

    PNG уже хранится внутри art_png — рисуем свой маленький логотип
    на PNGCanvas и заворачиваем в ICO: формат простой, без библиотек."""
    try:
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)]
        pngs = []
        for (w, h) in sizes:
            c = PNGCanvas(w, h, bg=(43, 26, 99))     # фиолетовый RB
            # рамка и «RB» пикселями: скруглённый квадрат + буквы
            c.frame(1, 1, w - 2, h - 2, (167, 139, 250), t=max(1, w // 16))
            c.line(w // 5, h // 4, w // 5, h * 3 // 4, (232, 232, 240),
                   t=max(1, w // 8))
            c.line(w // 2, h // 4, w * 4 // 5, h // 4, (232, 232, 240),
                   t=max(1, w // 8))
            c.line(w // 2, h // 4, w // 2, h // 2, (232, 232, 240),
                   t=max(1, w // 8))
            c.line(w // 2, h // 2, w * 4 // 5, h // 2, (232, 232, 240),
                   t=max(1, w // 8))
            c.line(w * 3 // 5, h // 2, w * 4 // 5, h * 3 // 4,
                   (232, 232, 240), t=max(1, w // 8))
            c.line(w * 3 // 5, h // 2, w * 3 // 5, h * 3 // 4,
                   (232, 232, 240), t=max(1, w // 8))
            c.line(w // 5, h * 3 // 4, w * 3 // 5, h * 3 // 4,
                   (232, 232, 240), t=max(1, w // 8))
            pngs.append(c.png())
        out = bytearray()
        out += struct.pack('<HHH', 0, 1, len(pngs))
        off = 6 + 16 * len(pngs)
        for (w, h), png in zip(sizes, pngs):
            out += struct.pack('<BBBBHHII', w % 256, h % 256, 0, 0,
                               1, 32, len(png), off)
            off += len(png)
        for png in pngs:
            out += png
        with open(path, 'wb') as f:
            f.write(bytes(out))
        return True
    except Exception as e:
        log('Не удалось записать иконку: %r' % e)
        return False


def _dark_title_bar(root):
    """v7: тёмный титул окна в стиле Windows 11 (DWMWA_USE_IMMERSIVE_DARK_MODE).

    На Windows 10 (1809+) и 11 шапка становится тёмной под цвет приложения;
    на старых системах и не-Windows тихо пропускается."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        for attr in (20, 19):        # DWMWA_USE_IMMERSIVE_DARK_MODE (20/19)
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), attr,
                ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
            if res == 0:
                break
    except Exception:
        pass


def run_gui():
    import tkinter as tk
    from tkinter import ttk
    from tkinter import font as tkfont

    if os.name == 'nt':
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # --- премиальная палитра v5: слои глубины, тонкие контуры ---
    BG = '#0a0a12'          # фон окна
    PANEL = '#12121e'       # панели
    PANEL_2 = '#171726'     # приподнятые элементы
    CHAT_BG = '#0d0d16'     # фон чата
    BUBBLE = '#1d1d38'      # пузырь ассистента (светлее фона чата —
                            # читается и на тёмных экранах ноутбуков)
    BUBBLE_U = '#6d28d9'    # пузырь пользователя
    IN_BG = '#151523'       # поле ввода
    HAIR = '#26263e'        # тонкие контуры (hairline)
    C_USER = '#fbbf24'
    C_BOT = '#93c5fd'
    C_TXT = '#ececf6'
    C_ERR = '#fca5a5'
    C_OK = '#86efac'
    C_META = '#8f8fa8'
    C_ACC = '#8b5cf6'
    C_ACC2 = '#a78bfa'
    C_CYAN = '#67e8f9'
    C_PINK = '#f0abfc'

    root = tk.Tk()
    root.title('%s v%s' % (APP_TITLE, APP_VERSION))
    # высота — под экран пользователя: на ноутбуках 1366x768 окно 840px
    # не помещалось и поле ввода оказывалось за нижней кромкой экрана
    try:
        scr_h = root.winfo_screenheight()
    except Exception:
        scr_h = 900
    win_h = max(660, min(840, scr_h - 60))
    root.geometry('660x%d' % win_h)
    root.minsize(520, 620)
    root.configure(bg=BG)
    # v7: тёмный титул в стиле Win11 + собственный значок
    _dark_title_bar(root)
    _apply_app_icon(root)

    FF = _ui_font_family()
    F_TITLE = tkfont.Font(family=FF, size=15, weight='bold')
    F_SUB = tkfont.Font(family=FF, size=9)
    F_LOGO = tkfont.Font(family=FF, size=15, weight='bold')
    F_NAME = tkfont.Font(family=FF, size=8, weight='bold')
    F_TXT = tkfont.Font(family=FF, size=10)
    F_META = tkfont.Font(family=FF, size=9, slant='italic')
    F_BTN = tkfont.Font(family=FF, size=10, weight='bold')
    F_AV = tkfont.Font(family=FF, size=11, weight='bold')
    F_CHIP = tkfont.Font(family=FF, size=9, weight='bold')

    style = ttk.Style(root)
    try:
        style.theme_use('clam')
        style.configure('TScrollbar', background=PANEL_2, troughcolor=CHAT_BG,
                        arrowcolor=C_META, bordercolor=CHAT_BG,
                        lightcolor=PANEL_2, darkcolor=PANEL_2)
    except Exception:
        pass

    # ---------- помощники рисования ----------
    def _lerp_hex(c1, c2, t):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return '#%02x%02x%02x' % tuple(
            int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _rrect(cv, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
               x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
               x0, y1, x0, y0 + r, x0, y0]
        return cv.create_polygon(pts, smooth=True, **kw)

    def _wrap(text, font, maxw):
        out = []
        for para in text.split('\n'):
            words = para.split(' ')
            cur = ''
            for w_ in words:
                t = (cur + ' ' + w_).strip()
                if not cur or font.measure(t) <= maxw:
                    cur = t
                else:
                    out.append(cur)
                    cur = w_
            out.append(cur)
        return out

    # ---------- шапка: градиент + mesh-свечение + пульс статуса ----------
    HEAD_H = 108
    head_cv = tk.Canvas(root, height=HEAD_H, highlightthickness=0, bg=BG)
    head_cv.pack(fill='x')
    pulse = {'on': False}
    head_state = {'key': None, 'min': None, 'size': 0}

    def _draw_header():
        head_cv.delete('all')
        W = head_cv.winfo_width()
        if W < 80:
            W = 660
        for x in range(W):
            head_cv.create_line(
                x, 0, x, HEAD_H - 2,
                fill=_lerp_hex('#1d1140', '#0b0b15', x / max(1, W - 1)))
        # mesh-свечение: полупрозрачные пятна
        for (cx, cy, r, col) in ((int(W * .84), 10, 140, '#3b1d6e'),
                                 (int(W * .10), 100, 120, '#0e3a4a'),
                                 (int(W * .55), -34, 110, '#4a1450')):
            for k in range(3):
                rr = r * (1 - k * 0.22)
                head_cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                    fill=col, outline='', stipple='gray12')
        # логотип: скруглённый квадрат с внутренним кольцом (RotoGo Beryllium)
        _rrect(head_cv, 18, 26, 64, 72, 14, fill=C_ACC, outline=C_ACC2)
        head_cv.create_rectangle(22, 30, 60, 68, outline='#c4b5fd')
        head_cv.create_text(41, 49, text='RB', fill='#ffffff', font=F_LOGO)
        head_cv.create_text(78, 22, text=APP_TITLE, fill='#ffffff',
                            font=F_TITLE, anchor='nw')
        head_cv.create_text(78, 54,
                            text=(('v%s · Gemini Flash · mini-apps · '
                                   'weather · rates · spreadsheets · timer'
                                   if LANG == 'en' else
                                   'v%s · Gemini Flash · мини-приложения · '
                                   'погода · курс · таблицы · таймер')
                                  % APP_VERSION),
                            fill=C_META, font=F_SUB, anchor='nw')
        # статус-чип с пульсирующей точкой
        has_key = bool(gemini_key())
        if LANG == 'en':
            label = 'Gemini connected' if has_key else 'Offline mode'
        else:
            label = 'Gemini подключён' if has_key else 'Офлайн-режим'
        cw = F_SUB.measure(label) + 42
        cy0, cy1 = 68, 92
        # часы слева от статус-чипа
        hm = time.strftime('%H:%M')
        clock_w = F_SUB.measure(hm) + 30
        cx1 = W - 16
        cx0 = cx1 - cw
        if has_key:
            _rrect(head_cv, cx0, cy0, cx1, cy1, 12, fill='#10291c',
                   outline='#1f7a45')
            head_cv.create_oval(cx0 + 12, cy0 + 8, cx0 + 24, cy0 + 20,
                                fill='#34d399' if pulse['on'] else '#6ee7b7',
                                outline='', tags=('pulse_dot',))
            head_cv.create_text(cx0 + 31, (cy0 + cy1) / 2, text=label,
                                fill='#a7f3d0', font=F_SUB, anchor='w')
        else:
            _rrect(head_cv, cx0, cy0, cx1, cy1, 12, fill=PANEL_2,
                   outline=HAIR)
            head_cv.create_oval(cx0 + 12, cy0 + 8, cx0 + 24, cy0 + 20,
                                fill='#565670', outline='')
            head_cv.create_text(cx0 + 31, (cy0 + cy1) / 2, text=label,
                                fill=C_META, font=F_SUB, anchor='w')
        # v7: часы — знают своё место, перекрывают пятно свечения
        # (без эмодзи: не у всех систем есть глиф в Tk; время и так видно)
        clk_x1 = cx0 - 10
        clk_x0 = clk_x1 - clock_w
        _rrect(head_cv, clk_x0, cy0, clk_x1, cy1, 12, fill=PANEL_2,
               outline=HAIR)
        head_cv.create_text(clk_x0 + 14, (cy0 + cy1) / 2, text='⏱',
                            font=F_SUB, anchor='w')
        head_cv.create_text(clk_x0 + clock_w - 12, (cy0 + cy1) / 2, text=hm,
                            fill='#d6d6ea', font=F_SUB, anchor='e')
        # трёхцветная линия внизу шапки
        for x in range(W):
            t = x / max(1, W - 1)
            if t < 0.5:
                c = _lerp_hex(C_CYAN, C_ACC, t * 2)
            else:
                c = _lerp_hex(C_ACC, C_PINK, (t - 0.5) * 2)
            head_cv.create_line(x, HEAD_H - 2, x, HEAD_H, fill=c)

    def _pulse():
        # v7: шапка перерисовывается только если что-то РЕАЛЬНО изменилось
        # (статус ключа/минута) — постоянной перерисовки нет, пульс точки
        # двигается через itemconfig. Иначе CPU зря тратился каждые 0.9 c.
        try:
            has_key = bool(gemini_key())
            state = (has_key, time.strftime('%H:%M'),
                     head_cv.winfo_width())
            if state != head_state['key']:
                head_state['key'] = state
                _draw_header()
            else:
                pulse['on'] = not pulse['on']
                if has_key:
                    # двигаем только точку статуса (без полной перерисовки)
                    items = head_cv.find_all()
                    for it in items:
                        try:
                            tags = head_cv.gettags(it)
                            if tags and tags[0] == 'pulse_dot':
                                head_cv.itemconfig(
                                    it, fill=('#34d399' if pulse['on']
                                              else '#6ee7b7'))
                        except Exception:
                            pass
        except Exception:
            pass
        root.after(900, _pulse)

    head_cv.bind('<Configure>', lambda e: _draw_header())

    # ---------- быстрые команды-чипы (v7: два ряда по 4) ----------
    chips_wrap = tk.Frame(root, bg=BG)
    chips_wrap.pack(fill='x', padx=16, pady=(10, 0))
    chips_row = tk.Frame(chips_wrap, bg=BG)
    chips_row.pack(side='top', fill='x')
    chips_row2 = tk.Frame(chips_wrap, bg=BG)
    chips_row2.pack(side='top', fill='x', pady=(6, 0))

    _QUICK_RU = (('помощь', 'помощь'),
                 ('погода', 'погода'),
                 ('курс валют', 'курс'),
                 ('таймер 5 мин', 'таймер на 5 минут'))
    _QUICK2_RU = (('презентация', 'сделай презентацию про '),
                  ('документ', 'создай текстовый документ про '),
                  ('таблица', 'создай таблицу про '),
                  ('анекдот', 'анекдот'))
    _QUICK_EN = (('help', 'help'),
                 ('weather', 'weather'),
                 ('rates', 'rates'),
                 ('timer 5m', 'timer for 5 minutes'))
    _QUICK2_EN = (('presentation', 'make a presentation about '),
                  ('document', 'create a text document about '),
                  ('spreadsheet', 'make a spreadsheet about '),
                  ('joke', 'joke'))

    def _run_chip(cmd):
        entry.focus_set()
        _ph_clear()
        entry.delete(0, 'end')
        entry.insert(0, cmd)
        entry.icursor('end')
        if not cmd.endswith(' '):
            send()

    def _mk_chip(label, cmd, row=0):
        w = F_CHIP.measure(label) + 26
        parent = chips_row if row == 0 else chips_row2
        cv = tk.Canvas(parent, width=w, height=28, bg=BG,
                       highlightthickness=0, cursor='hand2')

        def paint(fill, outline):
            cv.delete('all')
            _rrect(cv, 1, 1, w - 2, 27, 13, fill=fill, outline=outline)
            cv.create_text(w // 2, 14, text=label, fill='#d6d6ea', font=F_CHIP)
        paint(PANEL_2, HAIR)

        def enter(ev=None):
            paint('#2a2a46', C_ACC2)

        def leave(ev=None):
            paint(PANEL_2, HAIR)
        cv.bind('<Enter>', enter)
        cv.bind('<Leave>', leave)
        cv.bind('<Button-1>', lambda e: (leave(), _run_chip(cmd)))
        cv.pack(side='left', padx=(0, 8))
        return cv

    def _build_chips():
        for w_ in list(chips_row.winfo_children()) + list(chips_row2.winfo_children()):
            w_.destroy()
        quick = _QUICK_EN if LANG == 'en' else _QUICK_RU
        quick2 = _QUICK2_EN if LANG == 'en' else _QUICK2_RU
        for _lbl, _cmd in quick:
            _mk_chip(_lbl, _cmd, row=0)
        for _lbl, _cmd in quick2:
            _mk_chip(_lbl, _cmd, row=1)

    _build_chips()

    # ---------- чат: пузыри с тенями и хвостиками ----------
    chat_frame = tk.Frame(root, bg=BG)
    chat_frame.pack(fill='both', expand=True, padx=14, pady=(10, 4))
    chat_wrap = tk.Frame(chat_frame, bg=HAIR)
    chat_wrap.pack(fill='both', expand=True)
    chat_cv = tk.Canvas(chat_wrap, bg=CHAT_BG, highlightthickness=0,
                        cursor='arrow')
    sb = tk.Scrollbar(chat_wrap, command=chat_cv.yview, width=10,
                      bg=PANEL_2, troughcolor=CHAT_BG,
                      activebackground='#33335a', relief='flat',
                      borderwidth=0, highlightthickness=0)
    chat_cv.configure(yscrollcommand=sb.set, yscrollincrement=16)
    sb.pack(side='right', fill='y', padx=(0, 0), pady=1)
    chat_cv.pack(side='left', fill='both', expand=True, padx=1, pady=1)

    msgs = []                     # {who, kind, text, ts}
    ui = {'w': 0, 'stick': True, 'phase': 0, 'dots': [], 'anim': []}

    PAD_X, AV, GAP = 14, 32, 10
    NAME_H, GAP_NAME, GAP_MSG = 16, 5, 18
    PAD_BX, PAD_BY, R_AD = 14, 10, 16

    def _style(who, kind):
        if who == 'ТЫ':
            return {'bub': BUBBLE_U, 'txt': '#ffffff', 'name': C_USER,
                    'ring': '#8b5cf6', 'av': '#3b2a63', 'stripe': None,
                    'font': F_TXT, 'lh': 17, 'tail': 'r'}
        if kind == 'ok':
            return {'bub': '#122419', 'txt': '#c8f7d8', 'name': C_OK,
                    'ring': '#1f7a45', 'av': '#10291c', 'stripe': C_OK,
                    'font': F_TXT, 'lh': 17, 'tail': 'l'}
        if kind == 'err':
            return {'bub': '#2a151b', 'txt': '#ffd9df', 'name': C_ERR,
                    'ring': '#7a1f2d', 'av': '#331318', 'stripe': C_ERR,
                    'font': F_TXT, 'lh': 17, 'tail': 'l'}
        if kind == 'meta':
            return {'bub': '#141421', 'txt': '#9898ae', 'name': C_META,
                    'ring': HAIR, 'av': '#191927', 'stripe': None,
                    'font': F_META, 'lh': 15, 'tail': 'l'}
        if kind == 'progress':
            # живой статус: приглушённый пузырь с циановым маркером
            return {'bub': '#0f1a24', 'txt': '#8fd8e8', 'name': C_CYAN,
                    'ring': '#1e4254', 'av': '#0e2130', 'stripe': C_CYAN,
                    'font': F_META, 'lh': 15, 'tail': 'l'}
        return {'bub': BUBBLE, 'txt': C_TXT, 'name': C_BOT,
                'ring': '#34345a', 'av': '#22223c', 'stripe': None,
                'font': F_TXT, 'lh': 17, 'tail': 'l'}

    def _layout():
        W = chat_cv.winfo_width()
        if W < 80:
            W = 620
        ui['w'] = W
        chat_cv.delete('all')
        ui['anim'] = []          # [(item_id, born_at)] — плавный «пружинный» вход
        text_max = int((W - PAD_X * 2 - AV - GAP - PAD_BX * 2) * 0.97)
        y = 16
        now = time.time()
        for m in msgs:
            st = _style(m['who'], m['kind'])
            lines = _wrap(m['text'], st['font'], text_max)
            lw = max(st['font'].measure(ln) for ln in lines)
            bw = min(text_max + PAD_BX * 2, lw + PAD_BX * 2)
            bh = len(lines) * st['lh'] + PAD_BY * 2
            user = m['who'] == 'ТЫ'
            if user:
                bx1 = W - PAD_X - AV - GAP
                bx0 = bx1 - bw
                ax0 = W - PAD_X - AV
            else:
                bx0 = PAD_X + AV + GAP
                bx1 = min(bx0 + bw, W - PAD_X)
                ax0 = PAD_X
            by0 = y + NAME_H + GAP_NAME
            blk_h = NAME_H + GAP_NAME + bh
            avy0 = y + blk_h / 2.0 - AV / 2.0
            # v7: новые пузыри появляются чуть снизу и «всплывают»
            fresh = (now - m.get('born', 0)) < 0.45
            dy = 6 if fresh else 0
            # мягкая тень
            _rrect(chat_cv, bx0 + 2, by0 + 4, bx1 + 2, by0 + bh + 4, R_AD,
                   fill='#000000', outline='', stipple='gray25')
            # хвостик рисуем ПОВЕРХ корпуса: он заходит внутрь пузыря
            # и перекрывает контур — иначе на стыке видна тёмная щель
            bub_id = _rrect(chat_cv, bx0, by0, bx1, by0 + bh, R_AD,
                            fill=st['bub'], outline=st['ring'])
            if fresh:
                chat_cv.move(bub_id, 0, dy)
            if st['tail'] == 'l':
                p = chat_cv.create_polygon(bx0 + 6, by0 + bh - 10,
                                           bx0 + 30, by0 + bh - 10,
                                           bx0 + 30, by0 + bh + 1,
                                           bx0 + 16, by0 + bh + 9,
                                           bx0 + 6, by0 + bh + 1,
                                           fill=st['bub'], outline='')
                if fresh:
                    chat_cv.move(p, 0, dy)
            else:
                p = chat_cv.create_polygon(bx1 - 30, by0 + bh - 10,
                                           bx1 - 6, by0 + bh - 10,
                                           bx1 - 6, by0 + bh + 1,
                                           bx1 - 16, by0 + bh + 9,
                                           bx1 - 30, by0 + bh + 1,
                                           fill=st['bub'], outline='')
                if fresh:
                    chat_cv.move(p, 0, dy)
            if st['stripe']:
                _rrect(chat_cv, bx0 + 5, by0 + 8, bx0 + 9, by0 + bh - 8, 2,
                       fill=st['stripe'], outline='')
            ty = by0 + PAD_BY + (dy if fresh else 0)
            text_ids = []
            for ln in lines:
                text_ids.append(chat_cv.create_text(
                    bx0 + PAD_BX, ty, text=ln, fill=st['txt'],
                    font=st['font'], anchor='nw'))
                ty += st['lh']
            if fresh:
                for tid in text_ids:
                    chat_cv.move(tid, 0, dy)
            # v7: правая кнопка на пузыре копирует текст — привязки ниже
            # аватар с внешним кольцом
            chat_cv.create_oval(ax0 - 2, avy0 - 2, ax0 + AV + 2, avy0 + AV + 2,
                                fill='', outline=st['ring'])
            chat_cv.create_oval(ax0, avy0, ax0 + AV, avy0 + AV,
                                fill=st['av'], outline='')
            chat_cv.create_text(ax0 + AV / 2, avy0 + AV / 2,
                                text='Т' if user else 'А', fill='#ffffff',
                                font=F_AV)
            if user:
                chat_cv.create_text(bx1, y + 8, text=m['ts'], fill='#6d6d88',
                                    font=F_META, anchor='ne')
                chat_cv.create_text(bx1 - (F_META.measure(m['ts']) + 10),
                                    y + 8, text='ТЫ', fill=st['name'],
                                    font=F_NAME, anchor='ne')
            else:
                chat_cv.create_text(bx0, y + 8, text='ROTOGO',
                                    fill=st['name'], font=F_NAME, anchor='nw')
                chat_cv.create_text(bx0 + F_NAME.measure('ROTOGO') + 10,
                                    y + 8, text=m['ts'], fill='#6d6d88',
                                    font=F_META, anchor='nw')
            if fresh:
                for tid in [bub_id] + text_ids:
                    ui['anim'].append((tid, m.get('born', now)))
            y += blk_h + GAP_MSG
        ui['dots'] = []
        if typing_on.on:
            bx0 = PAD_X + AV + GAP
            _rrect(chat_cv, bx0 + 2, y + 4, bx0 + 78, y + 42, 14,
                   fill='#000000', outline='', stipple='gray25')
            _rrect(chat_cv, bx0, y, bx0 + 76, y + 38, 14,
                   fill=BUBBLE, outline='#34345a')
            for i in range(3):
                d = chat_cv.create_oval(bx0 + 16 + i * 18, y + 13,
                                        bx0 + 28 + i * 18, y + 25,
                                        fill='#a5a5e0' if i == ui['phase']
                                        else '#3d3d5c', outline='')
                ui['dots'].append(d)
            y += 54
        chat_cv.configure(scrollregion=(0, 0, W, y + 14))
        if ui['stick']:
            chat_cv.yview_moveto(1.0)

    def _anim_step():
        """v7: доводка «всплывания» новых пузырей (шаг 2 px, 30 мс)."""
        if ui['anim']:
            still = []
            for tid, born in ui['anim']:
                if time.time() - born < 0.45:
                    chat_cv.move(tid, 0, -2)
                    still.append((tid, born))
            ui['anim'] = still
        root.after(30, _anim_step)
    root.after(30, _anim_step)

    def _tick():
        if typing_on.on:
            ui['phase'] = (ui['phase'] + 1) % 3
            for i, d in enumerate(ui['dots']):
                chat_cv.itemconfig(d, fill='#a5a5e0' if i == ui['phase']
                                   else '#3d3d5c')
        root.after(280, _tick)
    root.after(280, _tick)

    def _on_conf(ev=None):
        if chat_cv.winfo_width() >= 80 and chat_cv.winfo_width() != ui['w']:
            _layout()
    chat_cv.bind('<Configure>', _on_conf)

    def _wheel(ev):
        try:
            if ev.num == 4 or getattr(ev, 'delta', 0) > 0:
                chat_cv.yview_scroll(-3, 'units')
            elif ev.num == 5 or getattr(ev, 'delta', 0) < 0:
                chat_cv.yview_scroll(3, 'units')
        except Exception:
            pass
        return 'break'
    chat_cv.bind('<MouseWheel>', _wheel)
    chat_cv.bind('<Button-4>', _wheel)
    chat_cv.bind('<Button-5>', _wheel)

    # ---------- ввод: поле со свечением фокуса + градиентные кнопки ----------
    input_row = tk.Frame(root, bg=BG)
    input_row.pack(fill='x', padx=14, pady=(4, 14))
    input_wrap = tk.Canvas(input_row, height=54, bg=BG, highlightthickness=0)
    input_wrap.pack(side='left', fill='x', expand=True)
    entry = tk.Entry(input_wrap, bg=IN_BG, fg='#f4f4fa',
                     insertbackground='#f4f4fa', relief='flat',
                     font=(FF, 11), highlightthickness=0)
    def _ph_text():
        return ('Ask something or type a command…' if LANG == 'en'
                else 'Спросите что-нибудь или напишите команду…')
    input_focus = {'on': False}

    def _draw_input():
        input_wrap.delete('all')
        w = input_wrap.winfo_width()
        if w < 60:
            w = 470
        if input_focus['on']:
            # мягкое свечение фокуса (внешний слой)
            _rrect(input_wrap, 0, 0, w - 1, 53, 17, fill='#241a3f',
                   outline='')
        _rrect(input_wrap, 1, 1, w - 2, 52, 16, fill=IN_BG,
               outline=C_ACC2 if input_focus['on'] else HAIR)
        input_wrap.create_window(16, 26, window=entry, width=w - 34,
                                 height=30, anchor='w')

    def _ph_set():
        entry.delete(0, 'end')
        entry.insert(0, _ph_text())
        entry.config(fg='#6b6b85')

    def _ph_clear():
        if entry.get() == _ph_text():
            entry.delete(0, 'end')
            entry.config(fg='#f4f4fa')

    def _ph_in(ev=None):
        input_focus['on'] = True
        _ph_clear()
        _draw_input()

    def _ph_out(ev=None):
        input_focus['on'] = False
        if not entry.get():
            _ph_set()
        _draw_input()

    entry.bind('<FocusIn>', _ph_in)
    entry.bind('<FocusOut>', _ph_out)
    input_wrap.bind('<Configure>', lambda e: _draw_input())
    input_wrap.bind('<Button-1>', lambda e: entry.focus_set())

    def _pill(w, h, text, base, top, hover, fg):
        """Кнопка-пилюля; top — цвет верхней половины (эффект градиента).
        text может быть строкой или функцией -> строка (для i18n)."""
        cv = tk.Canvas(input_row, width=w, height=h, bg=BG,
                       highlightthickness=0, cursor='hand2')
        state = {'fill': base}

        def label_now():
            return text() if callable(text) else text

        def paint(fill_main):
            state['fill'] = fill_main
            cv.delete('all')
            _rrect(cv, 1, 1, w - 2, h - 2, (h - 2) // 2, fill=fill_main,
                   outline='')
            if top:
                _rrect(cv, 3, 3, w - 4, h // 2, (h - 4) // 2, fill=top,
                       outline='')
            cv.create_text(w // 2, h // 2 + (1 if top else 0),
                           text=label_now(), fill=fg, font=F_BTN)
        paint(base)

        def enter(ev=None):
            paint(hover)

        def leave(ev=None):
            paint(base)
        cv.bind('<Enter>', enter)
        cv.bind('<Leave>', leave)
        cv.repaint = lambda: paint(state['fill'])
        return cv

    _LBL_PASTE = lambda: ('Paste' if LANG == 'en' else 'Вставить')
    _LBL_SEND = lambda: ('Send' if LANG == 'en' else 'Отправить')
    paste_pill = _pill(100, 54, _LBL_PASTE, PANEL_2, None, '#2b2b48',
                       '#dcdcf0')
    paste_pill.pack(side='right', padx=(0, 8))
    send_pill = _pill(128, 54, _LBL_SEND, '#7c3aed', '#8b5cf6',
                      '#6d28d9', '#ffffff')
    send_pill.pack(side='right')

    brain = Assistant()
    out_q = queue.Queue()
    cmd_q = queue.Queue()
    progress_q = queue.Queue()   # v6: живые статусы длинных операций
    pending = {'n': 0}

    def _on_progress(text):
        """Асессистент сообщает «что делает» — из воркер-потока в чат."""
        progress_q.put(text)

    brain.on_progress = _on_progress

    def add_msg(who, text, kind='bot_text'):
        ui['stick'] = chat_cv.yview()[1] >= 0.995 or not msgs
        # v7.1: перевод на язык интерфейса (кроме ввода пользователя)
        if who == 'ТЫ' and LANG == 'en':
            who = 'YOU'
        if kind != 'user_text':
            text = _tr(text)
        # v7: прогресс живёт в ОДНОМ пузыре — чат не забивается строчками
        if kind == 'progress':
            last = msgs[-1] if msgs else None
            if last and last['kind'] == 'progress':
                last['text'] = text.rstrip()
                last['ts'] = time.strftime('%H:%M')
                _layout()
                return
        msgs.append({'who': who, 'kind': kind, 'text': text.rstrip(),
                     'ts': time.strftime('%H:%M'),
                     'born': time.time()})
        _layout()
    add_msg.first = True    # совместимость со старым обращением

    def clear_chat():
        del msgs[:]
        chat_cv.delete('all')
        add_msg.first = True
        welcome()

    def typing_on():
        if typing_on.on:
            return
        typing_on.on = True
        ui['stick'] = chat_cv.yview()[1] >= 0.995 or not msgs
        _layout()
    typing_on.on = False

    def typing_off():
        if not typing_on.on:
            return
        typing_on.on = False
        _layout()

    def welcome():
        if LANG == 'en':
            if gemini_key():
                gem_line = ('— text is written by Google Gemini (key connected, '
                            'working model is remembered);\n')
            else:
                gem_line = ('— text: Gemini (command "connect google"), '
                            'Wikipedia or the offline knowledge base;\n')
            text = (('Hello! I am %s v%s — the FINAL version.\n\n'
                     'What is new in Beryllium FINAL:\n'
                     + gem_line +
                     '— mini-apps in chat: weather, Central Bank rates, '
                     'calculator, timer, translation, coin/dice;\n'
                     '— new documents: Excel spreadsheets (.xlsx) with a header '
                     'row and autofilter; file search "find file …";\n'
                     '— speed: topic and Wikipedia title caching — a repeat '
                     'presentation on a familiar topic is assembled instantly;\n'
                     '— interface: floating bubbles, a clock in the header, '
                     'input history with Up/Down arrows, copy messages with '
                     'right-click.\n\n'
                     'Type "help" to see all commands. Switch language: "russian".')
                    % (APP_TITLE, APP_VERSION))
        else:
            if gemini_key():
                gem_line = ('— текст пишет Google Gemini (ключ подключён, '
                            'рабочая модель запоминается);\n')
            else:
                gem_line = ('— текст: Gemini (команда «подключи гугл»), '
                            'Википедия или офлайн-база знаний;\n')
            text = (('Привет! Я %s v%s — ФИНАЛЬНАЯ версия.\n\n'
                     'Что нового в Beryllium FINAL:\n'
                     + gem_line +
                     '— мини-приложения в чате: погода, курсы валют ЦБ, '
                     'калькулятор, таймер, перевод, монетка/кубик;\n'
                     '— новые документы: таблицы Excel (.xlsx) с шапкой '
                     'и автофильтром; поиск файлов «найди файл …»;\n'
                     '— скорость: кэш тем и названий статей Википедии — '
                     'повторная презентация по знакомой теме собирается '
                     'мгновенно;\n'
                     '— интерфейс: плавающие пузыри, часы в шапке, история '
                     'ввода стрелками ↑/↓, копирование сообщений правой '
                     'кнопкой мыши.\n\n'
                     'Напишите «помощь» — покажу все команды. Язык: «english».')
                    % (APP_TITLE, APP_VERSION))
        add_msg('ROTOGO', text, 'bot_text')

    # v7: история ввода — стрелки вверх/вниз листают прошлые команды
    hist = {'items': [], 'pos': -1, 'saved': ''}

    def _hist_add(text):
        if text and (not hist['items'] or hist['items'][-1] != text):
            hist['items'].append(text)
            if len(hist['items']) > 60:
                hist['items'].pop(0)
        hist['pos'] = -1

    def _hist_up(ev=None):
        if not hist['items']:
            return 'break'
        if hist['pos'] == -1:
            hist['saved'] = entry.get()
            hist['pos'] = len(hist['items']) - 1
        elif hist['pos'] > 0:
            hist['pos'] -= 1
        _ph_clear()
        entry.delete(0, 'end')
        entry.insert(0, hist['items'][hist['pos']])
        entry.icursor('end')
        return 'break'

    def _hist_down(ev=None):
        if hist['pos'] == -1:
            return 'break'
        if hist['pos'] < len(hist['items']) - 1:
            hist['pos'] += 1
            val = hist['items'][hist['pos']]
        else:
            hist['pos'] = -1
            val = hist['saved']
        _ph_clear()
        entry.delete(0, 'end')
        entry.insert(0, val)
        entry.icursor('end')
        return 'break'

    entry.bind('<Up>', _hist_up)
    entry.bind('<Down>', _hist_down)

    # v7: таймер — по срабатыванию окно + пузырь в чат + звук (MessageBeep)
    timers = {'n': 0}

    def _on_timer(secs, label):
        label_txt = label or (('timer for %s' if LANG == 'en'
                               else 'таймер на %s') % _human_secs(secs))
        timers['n'] += 1

        def fire():
            chat_msg = (('⏰ TIME IS UP!\n%s — elapsed %s.'
                         if LANG == 'en' else
                         '⏰ ВРЕМЯ ВЫШЛО!\n%s — прошло %s.')
                        % (label_txt, _human_secs(secs)))
            add_msg('ROTOGO', chat_msg, 'ok')
            try:
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.user32.MessageBeep(0xFFFFFFFF)
                else:
                    try:
                        root.bell()
                    except Exception:
                        pass
            except Exception:
                try:
                    root.bell()
                except Exception:
                    pass
            try:
                import tkinter.messagebox as _mb
                mb_title = ('Timer — RotoGo Beryllium' if LANG == 'en'
                            else 'Таймер — RotoGo Beryllium')
                mb_body = (("Time's up!\n\n%s\n(elapsed %s)"
                            if LANG == 'en' else
                            'Время вышло!\n\n%s\n(прошло %s)')
                           % (label_txt, _human_secs(secs)))
                root.after(0, lambda: _mb.showinfo(mb_title, mb_body))
            except Exception:
                pass
            # вторая «нотка» через секунду — заметнее
            def again():
                try:
                    root.bell()
                except Exception:
                    pass
            root.after(1000, again)
        root.after(int(secs * 1000), fire)

    brain.on_timer = _on_timer

    def send(event=None):
        text = entry.get().strip()
        if not text or text == _ph_text().strip():
            return
        _hist_add(text)
        _ph_set()
        add_msg('ТЫ', text, 'user_text')
        log('ПОЛЬЗОВАТЕЛЬ: %s' % text)
        pending['n'] += 1
        typing_on()
        cmd_q.put(text)

    # ------------------------------------------------- вставка в поле ввода
    # При русской раскладке Ctrl+V порождает клавишу Cyrillic_ve, и
    # стандартная привязка <Control-v> в Tk не срабатывает. Поэтому:
    # 1) кириллические клавиши явно запускаем виртуальные события Tk;
    # 2) правая кнопка мыши открывает меню с «Вставить»;
    # 3) рядом с полем есть кнопка «Вставить»;
    # 4) ключ можно подключить выбором файла, без копирования вовсе.

    def _entry_paste(event=None):
        entry.focus_set()
        _ph_clear()
        try:
            clip = entry.clipboard_get()
        except Exception:
            clip = ''
        if not clip:
            return 'break'
        try:
            entry.delete('sel.first', 'sel.last')      # замена выделенного
        except Exception:
            pass
        entry.insert('insert', clip)
        entry.icursor('end')
        entry.xview_moveto(1.0)
        return 'break'

    def _entry_copy(event=None):
        try:
            entry.event_generate('<<Copy>>')
        except Exception:
            pass
        return 'break'

    def _entry_cut(event=None):
        try:
            entry.event_generate('<<Cut>>')
        except Exception:
            pass
        return 'break'

    def _entry_select_all(event=None):
        entry.focus_set()
        entry.select_range(0, 'end')
        entry.icursor('end')
        return 'break'

    # клавиатурные сокращения при ЛЮБОЙ раскладке: обработчик смотрит
    # имя клавиши В МОМЕНТ НАЖАТИЯ (работает на любой системе).
    _CTRL_ACT = {'cyrillic_ve': _entry_paste,        # В = физическая V
                 'cyrillic_es': _entry_copy,         # С = физическая C
                 'cyrillic_che': _entry_cut,         # Ч = физическая X
                 'cyrillic_ef': _entry_select_all,   # А = физическая A
                 'a': _entry_select_all}             # Ctrl+A на латинице

    def _ctrl_key(event):
        fn = _CTRL_ACT.get(str(event.keysym).lower())
        if fn:
            fn()
            return 'break'
        return None

    try:
        root.bind_all('<Control-KeyPress>', _ctrl_key)
    except Exception:
        pass

    # клик по чату возвращает фокус в поле ввода
    chat_cv.bind('<Button-1>', lambda e: entry.focus_set())

    # v7: правая кнопка на пузыре копирует текст сообщения
    def _bubble_text_at(y):
        """Ищет сообщение, чей блок пересекает вертикальную координату."""
        # вычисляем границы блоков так же, как _layout (без рисования)
        W = ui['w'] or 620
        text_max = int((W - PAD_X * 2 - AV - GAP - PAD_BX * 2) * 0.97)
        ytop = 16
        for m in msgs:
            st = _style(m['who'], m['kind'])
            lines = _wrap(m['text'], st['font'], text_max)
            bh = len(lines) * st['lh'] + PAD_BY * 2
            blk_h = NAME_H + GAP_NAME + bh
            if ytop <= y <= ytop + blk_h:
                return m
            ytop += blk_h + GAP_MSG
        return None

    def _chat_context(ev):
        m = _bubble_text_at(ev.y)
        if not m:
            return 'break'
        clip_text = m['text']
        try:
            root.clipboard_clear()
            root.clipboard_append(clip_text)
            add_msg('ROTOGO',
                    ('Copied message text (%d chars) to the clipboard.'
                     if LANG == 'en' else
                     'Скопировал текст сообщения (%d симв.) '
                     'в буфер обмена.') % len(clip_text), 'meta')
        except Exception:
            pass
        return 'break'

    chat_cv.bind('<Button-3>', _chat_context)

    # правая кнопка мыши на поле ввода — меню
    ctx_menu = tk.Menu(root, tearoff=0, bg=PANEL, fg='#ffffff',
                       activebackground=C_ACC, activeforeground='#ffffff',
                       font=(FF, 10))

    def _ctx_update():
        sel = bool(entry.selection_present())
        entry_state = 'normal'
        ctx_menu.entryconfig(0, state=entry_state if sel else 'disabled')
        ctx_menu.entryconfig(1, state=entry_state if sel else 'disabled')
        try:
            has_clip = bool(entry.clipboard_get())
        except Exception:
            has_clip = False
        ctx_menu.entryconfig(2, state=entry_state if has_clip else 'disabled')
        ctx_menu.entryconfig(3, state=entry_state)

    def _ctx_show(event):
        try:
            _ctx_update()
            ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            ctx_menu.grab_release()
        return 'break'

    def _ctx_labels():
        if LANG == 'en':
            return ('Copy', 'Cut', 'Paste', 'Select all')
        return ('Копировать', 'Вырезать', 'Вставить', 'Выделить всё')

    ctx_menu.add_command(label=_ctx_labels()[0], command=_entry_copy)
    ctx_menu.add_command(label=_ctx_labels()[1], command=_entry_cut)
    ctx_menu.add_command(label=_ctx_labels()[2], command=_entry_paste)
    ctx_menu.add_command(label=_ctx_labels()[3], command=_entry_select_all)

    def _ctx_refresh_labels():
        for i, lbl in enumerate(_ctx_labels()):
            try:
                ctx_menu.entryconfig(i, label=lbl)
            except Exception:
                pass
    entry.bind('<Button-3>', _ctx_show)
    entry.bind('<Button-2>', _ctx_show)   # средняя кнопка на некоторых мышах
    paste_pill.bind('<Button-1>', lambda e: _entry_paste())

    def ask_key_file():
        """Подключение ключа выбором файла (главный поток Tk)."""
        from tkinter.filedialog import askopenfilename
        if LANG == 'en':
            _title = 'Select the file with the API key'
            _ftypes = [('Text files', '*.txt'), ('All files', '*.*')]
        else:
            _title = 'Выберите файл с API-ключом'
            _ftypes = [('Текстовые файлы', '*.txt'), ('Все файлы', '*.*')]
        path = askopenfilename(title=_title, filetypes=_ftypes)
        if not path:
            add_msg('ROTOGO', 'Файл не выбран — ключ не менялся.', 'meta')
            return
        try:
            # utf-8-sig — Блокнот Windows часто сохраняет с BOM
            with open(path, encoding='utf-8-sig', errors='replace') as f:
                lines = [ln.strip() for ln in f.read().splitlines()]
        except Exception as e:
            add_msg('ROTOGO', 'Не удалось прочитать файл: %s' % e, 'err')
            return
        lines = [ln for ln in lines if ln and not ln.startswith('#')]
        key = lines[0].strip().strip(' «»"\'') if lines else ''
        if len(key) < 16 or ' ' in key:
            add_msg('ROTOGO',
                    'В файле не похоже на ключ: нужна ОДНА строка не короче '
                    '16 символов без пробелов (AIza… или AQ.…). '
                    'Файл: %s' % path, 'err')
            return
        for msg, knd in brain._save_key(key):
            add_msg('ROTOGO', msg, kind_map.get(knd, knd))
        _draw_header()

    def worker():
        while True:
            text = cmd_q.get()
            try:
                replies = brain.handle(text)
            except Exception as e:
                log('ОШИБКА воркера: %r' % e)
                replies = [('Внутренняя ошибка: %s' % e, 'err')]
            time.sleep(0.35)
            out_q.put(replies)

    kind_map = {'text': 'bot_text', 'progress': 'progress'}
    key_state = {'has': None}

    def poll():
        changed = False
        try:
            while True:
                ptxt = progress_q.get_nowait()
                add_msg('ROTOGO', ptxt, 'progress')
                changed = True
        except queue.Empty:
            pass
        try:
            while True:
                replies = out_q.get_nowait()
                changed = True
                pending['n'] = max(0, pending['n'] - 1)
                typing_off()
                for msg, kind in replies:
                    if kind == 'cmd':
                        if msg == '__CLEAR__':
                            clear_chat()
                        elif msg == '__EXIT__':
                            root.after(1200, root.destroy)
                        elif msg == '__ASKFILE__':
                            # Диалог и чтение файла — только в главном потоке Tk
                            ask_key_file()
                        continue
                    add_msg('ROTOGO', msg, kind_map.get(kind, kind))
        except queue.Empty:
            pass
        if changed:
            # статус-чип мог измениться (ключ подключили/удалили)
            has = bool(gemini_key())
            if has != key_state['has']:
                key_state['has'] = has
                _draw_header()
        # v7.1: команда «язык/english» сменила LANG в воркере — обновим интерфейс
        if LANG != _lang_seen['v']:
            _lang_seen['v'] = LANG
            _refresh_lang()
        # v7: 70 мс вместо 90 — реакции чата неотличимы от мгновенных
        root.after(70, poll)

    def _first_key(ev):
        if str(ev.keysym).lower() in ('control_l', 'control_r', 'shift_l',
                                      'shift_r', 'alt_l', 'alt_r',
                                      'meta_l', 'meta_r'):
            return
        _ph_clear()

    entry.bind('<Return>', send)
    send_pill.bind('<Button-1>', lambda e: send())
    entry.bind('<Key>', _first_key)

    # v7.1: кнопка переключения языка RU/EN в шапке + обновление интерфейса.
    # Команда «язык/english» меняет LANG в воркер-потоке (set_lang refresh=False),
    # а poll() в главном потоке замечает смену и вызывает _refresh_lang — так
    # Tk не дёргается из чужого потока.
    def _refresh_lang():
        try:
            _build_chips()
            _draw_header()
            _ctx_refresh_labels()
            paste_pill.repaint()
            send_pill.repaint()
            _ph_set()
            lang_btn.config(text='EN' if LANG == 'en' else 'RU')
        except Exception as e:
            log('обновление языка: %r' % e)

    def _toggle_lang():
        set_lang('toggle', refresh=False)
        _refresh_lang()

    lang_btn = tk.Button(
        root, text=('EN' if LANG == 'en' else 'RU'),
        command=_toggle_lang, bg=PANEL_2, fg=C_TXT,
        activebackground='#2b2b48', activeforeground=C_TXT,
        bd=0, font=F_SUB, padx=10, pady=2, highlightthickness=0,
        cursor='hand2')
    lang_btn.place(relx=1.0, rely=0.0, x=-10, y=8, anchor='ne')

    _lang_seen = {'v': LANG}

    threading.Thread(target=worker, daemon=True).start()
    _ph_set()
    _draw_header()
    welcome()
    entry.focus_set()
    root.after(70, poll)
    root.after(900, _pulse)
    # v6: прогрев проверки сети в фоне — первая команда не ждёт 5-10 сек
    root.after(150, lambda: threading.Thread(
        target=net_available, daemon=True).start())
    root.mainloop()

def _prepare():
    # pythonw (.pyw) не даёт потоков вывода — подменяем, чтобы print не падал
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    detach_from_console()
    _load_lang()   # v7.1: язык интерфейса из lang.txt (по умолчанию 'ru')


def _fatal(err):
    """Любая ошибка запуска обязана стать видимой: error_log.txt + окно."""
    import traceback
    details = traceback.format_exc()
    try:
        with open(os.path.join(_script_dir(), 'error_log.txt'), 'w',
                  encoding='utf-8') as f:
            f.write('%s v%s - ошибка запуска\n\n%s' %
                    (APP_TITLE, APP_VERSION, details))
    except Exception:
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk()
        _r.withdraw()
        _mb.showerror(
            APP_TITLE + ' - не удалось запуститься',
            'Программа не смогла открыться.\n\nПричина: %r\n\n'
            'Подробности записаны в файл error_log.txt\n'
            '(лежит рядом с программой).' % (err,))
        _r.destroy()
    except Exception:
        pass


if __name__ == '__main__':
    _prepare()
    log('=== СТАРТ %s v%s ===' % (APP_TITLE, APP_VERSION))
    try:
        run_gui()
    except Exception as e:
        log('КРИТИЧЕСКАЯ ОШИБКА: %r' % e)
        _fatal(e)
