# -*- coding: utf-8 -*-
"""
هسته‌ی پایتونی ربات (سلف‌بات سروش، چند اکانت) - ساخته شده توسط پارسا
این فایل داخل اپ اندروید (Chaquopy) اجرا می‌شه و از طرف Kotlin کنترل می‌شه.
- لیست فحش بین همه‌ی اکانت‌ها مشترکه
- بقیه‌ی لیست‌ها و تنظیمات برای هر اکانت جداست
- پیام‌های خود اکانت همیشه به‌عنوان دستور حساب می‌شن (مثلا /help)
"""
import asyncio
import collections
import copy
import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from splusthon import SoroushClient, events
from splusthon.sessions import StringSession

DATA_DIR = "."
ACC_FILE = "accounts.json"
SHARED_FILE = "self_shared.json"

MIN_SPAM_INTERVAL = 3     # حداقل فاصله‌ی اسپم (ثانیه) تا اکانت محدود نشه
ENEMY_COOLDOWN = 2        # حداقل فاصله‌ی جواب به یک نفر (ثانیه)

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
TIME_RE = re.compile(r"\s*\d{2}:\d{2}\s*$")

LOG = collections.deque(maxlen=80)


def log(msg):
    LOG.append(time.strftime("%H:%M:%S") + "  " + str(msg))


def bold_digits(s):
    """ارقام انگلیسی رو به ارقام پررنگ یونیکد تبدیل می‌کنه"""
    return "".join(chr(0x1D7CE + int(c)) if c.isdigit() and c.isascii() else c for c in s)


logging.basicConfig(level=logging.WARNING)
logging.getLogger("splusthon").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

_MENTION_RE = re.compile(r"\[([^\]]*)\]\(tg://user\?id=\d+\)")


# ================== ذخیره‌سازی ==================
def _write_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log(f"خطا در ذخیره {os.path.basename(path)}: {e}")


def _read_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"خطا در خواندن {os.path.basename(path)}: {e}")
    return default


shared = {"fosh_list": []}


def save_shared():
    _write_json(SHARED_FILE, shared)


DEFAULT_CONFIG = {
    "enemy_list": [],
    "silence_list": [],
    "spam_list": [],
    "spam_time": 5,
    "enemy_reply": 1,
    "timer_spam_list": [],
    "timer_minutes": 5,
    "timer_text": "$",
    "timer_on": False,
    "intro_text": "",
    "clock_on": False,
}


def init(data_dir):
    """یک بار از طرف اپ صدا زده می‌شه"""
    global DATA_DIR, ACC_FILE, SHARED_FILE
    DATA_DIR = data_dir
    os.makedirs(DATA_DIR, exist_ok=True)
    ACC_FILE = os.path.join(DATA_DIR, "accounts.json")
    SHARED_FILE = os.path.join(DATA_DIR, "self_shared.json")
    loaded = _read_json(SHARED_FILE, {})
    if isinstance(loaded, dict) and isinstance(loaded.get("fosh_list"), list):
        shared["fosh_list"] = loaded["fosh_list"]
    _ensure_loop()
    return "OK"


class Account:
    def __init__(self, spec):
        self.name = spec["name"]
        self.phone = spec.get("phone", "")
        self.admin_id = spec.get("admin_id")
        self.config_file = os.path.join(DATA_DIR, f"cfg_{self.name}.json")
        self.client = SoroushClient(StringSession(spec["session"]))
        self.cfg = self._load()
        self.is_off = False
        self.connected = False
        self.typing_ids = set()
        self.tasks = {}
        self.enemy_last = {}
        self.clock_base = None
        self.client.on(events.NewMessage)(self.on_message)

    # ---------- ذخیره ----------
    def _load(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        data = _read_json(self.config_file, {})
        if isinstance(data, dict):
            data.pop("fosh_list", None)
            cfg.update(data)
        return cfg

    def save(self):
        _write_json(self.config_file, self.cfg)

    # ---------- ارسال امن ----------
    async def send(self, chat_id, text):
        try:
            return await self.client.send_message(chat_id, text)
        except Exception:
            try:
                return await self.client.send_message(
                    chat_id, _MENTION_RE.sub(r"\1", text), parse_mode=None)
            except Exception as e:
                log(f"[{self.name}] خطا در ارسال به {chat_id}: {e!r}")
                return None

    async def say(self, event, text):
        try:
            return await event.reply(text)
        except Exception:
            try:
                return await event.reply(_MENTION_RE.sub(r"\1", text), parse_mode=None)
            except Exception as e:
                log(f"[{self.name}] خطا در پاسخ: {e!r}")
                return None

    def pick_text(self):
        if not shared["fosh_list"]:
            return "__لیست فحش ها خالی است!__"
        return self.cfg["intro_text"] + random.choice(shared["fosh_list"])

    # ---------- تسک‌های پس‌زمینه ----------
    def ensure_task(self, name, factory):
        t = self.tasks.get(name)
        if t is None or t.done():
            self.tasks[name] = asyncio.ensure_future(factory())

    def stop_task(self, name):
        t = self.tasks.pop(name, None)
        if t:
            t.cancel()

    def stop_all(self):
        for n in list(self.tasks):
            self.stop_task(n)

    def start_background(self):
        if self.cfg["spam_list"]:
            self.ensure_task("spam", self.spam_loop)
        if self.cfg["timer_on"]:
            self.ensure_task("timer", self.timer_loop)
        if self.cfg.get("clock_on"):
            self.ensure_task("clock", self.clock_loop)

    async def spam_loop(self):
        while self.cfg["spam_list"]:
            if not self.is_off:
                for cid in list(self.cfg["spam_list"]):
                    await self.send(cid, self.pick_text())
                    await asyncio.sleep(0.3)
            await asyncio.sleep(max(MIN_SPAM_INTERVAL, self.cfg["spam_time"]))

    async def timer_loop(self):
        while self.cfg["timer_on"]:
            if not self.is_off and self.cfg["timer_spam_list"] and self.cfg["timer_text"]:
                for cid in list(self.cfg["timer_spam_list"]):
                    await self.send(cid, self.cfg["timer_text"])
                    await asyncio.sleep(0.3)
            await asyncio.sleep(max(60, int(self.cfg["timer_minutes"]) * 60))

    async def typing_loop(self):
        while self.typing_ids:
            if not self.is_off:
                for cid in list(self.typing_ids):
                    try:
                        async with self.client.action(cid, "typing"):
                            await asyncio.sleep(1)
                    except Exception:
                        self.typing_ids.discard(cid)
            await asyncio.sleep(4)

    # ---------- ساعت کنار اسم ----------
    async def set_first_name(self, name):
        name = name[:64]
        try:
            from splusthon.tl.functions.account import UpdateProfileRequest
        except ImportError:
            UpdateProfileRequest = None
        if UpdateProfileRequest is not None:
            return await self.client(UpdateProfileRequest(first_name=name))
        for method in ("update_profile", "edit_profile", "set_profile", "update_name"):
            fn = getattr(self.client, method, None)
            if fn:
                return await fn(first_name=name)
        raise RuntimeError("متد تغییر پروفایل پیدا نشد")

    async def restore_name(self):
        if self.clock_base:
            try:
                await self.set_first_name(self.clock_base)
            except Exception as e:
                log(f"[{self.name}] برگردوندن اسم اصلی نشد: {e!r}")

    async def clock_loop(self):
        try:
            me = await self.client.get_me()
            self.clock_base = TIME_RE.sub("", getattr(me, "first_name", "") or "").strip()
        except Exception as e:
            log(f"[{self.name}] گرفتن اسم اکانت نشد: {e!r}")
            self.cfg["clock_on"] = False
            self.save()
            return
        log(f"[{self.name}] ساعت روشن شد؛ اسم اصلی: {self.clock_base}")
        last = None
        while self.cfg["clock_on"]:
            now = datetime.now(IRAN_TZ).strftime("%H:%M")
            if now != last:
                try:
                    await self.set_first_name(f"{self.clock_base} {bold_digits(now)}")
                    last = now
                except RuntimeError as e:
                    log(f"[{self.name}] {e}")
                    self.cfg["clock_on"] = False
                    self.save()
                    return
                except Exception as e:
                    log(f"[{self.name}] خطا در آپدیت ساعت: {e!r}")
            sec = datetime.now(IRAN_TZ).second
            await asyncio.sleep(60 - sec + 0.5)

    # ---------- هندلر پیام ----------
    async def on_message(self, event):
        try:
            raw = (event.raw_text or event.text or "").strip()
            sender = event.sender_id
            is_admin = bool(getattr(event, "out", False)) or (
                self.admin_id is not None and sender == self.admin_id)

            if is_admin and raw.startswith("/"):
                parts = raw.split()
                cmd = parts[0][1:].split("@")[0].lower()
                fn = COMMANDS.get(cmd)
                if fn:
                    if self.is_off and cmd not in ("bot", "restart"):
                        return
                    await fn(self, event, parts[1:], raw)
                    return

            if self.is_off or sender is None:
                return

            # دشمن
            if sender in self.cfg["enemy_list"]:
                key = (event.chat_id, sender)
                now = time.time()
                if now - self.enemy_last.get(key, 0) >= ENEMY_COOLDOWN:
                    self.enemy_last[key] = now
                    txt = self.pick_text()
                    if self.cfg["enemy_reply"]:
                        await self.say(event, txt)
                    else:
                        await self.send(event.chat_id, txt)

            # سکوت
            if sender in self.cfg["silence_list"]:
                try:
                    await event.delete()
                except Exception:
                    pass
        except Exception as e:
            log(f"[{self.name}] خطای پردازش پیام: {e!r}")


# ================== کمکی‌ها ==================
HELP_TEXT = """
🌲 راهنمای سلف‌بات 🌲
`/ping` | `/help` | `/restart` (فقط تنظیمات همین اکانت)
`/bot` on|off — روشن/خاموش کردن همین اکانت
`/id` — آیدی عددی (گروه، پیوی یا ریپلای)
`/settime` عدد — فاصله‌ی اسپم (ثانیه)
`/reply` on|off — ریپلای به دشمن
`/typing` on|off — حالت تایپینگ
◈━━ فحش (مشترک بین همه‌ی اکانت‌ها) ━━◈
`/addfosh` (ریپلای) | `/addallfosh` (ریپلای، خط‌به‌خط)
`/delfosh` (ریپلای) | `/flist` | `/cleanflist`
◈━━━━━ دشمن ━━━━━◈
`/setenemy` (آیدی | ریپلای | پیوی) | `/delenemy`
`/enemylist` | `/cleanlist`
◈━━━━━ سکوت ━━━━━◈
`/add` آیدی | `/del` آیدی | `/dellist`
◈━━━━━ اسپم ━━━━━◈
`/setspam` (آیدی | ریپلای | همین چت) | `/spamlist` | `/cleanslist`
`/settext` متن (یا ریپلای برای تگ) | `/deltext`
◈━━━━━ تایمر ━━━━━◈
`/timer` on|off | `/pingtimer`
`/timertext` (ریپلای) | `/settimer` دقیقه
`/setspamtimer` | `/listspamtimer`
`/deltimerspam` آیدی | `/cleanlisttimer`
◈━━━━━ دیگر ━━━━━◈
`/name` (ریپلای) — تغییر اسم اکانت
`/clock` on|off — ساعت کنار اسم اکانت (وقت تهران)
"""


async def reply_target_id(event):
    if event.is_reply:
        msg = await event.get_reply_message()
        if msg is not None and msg.sender_id is not None:
            return msg.sender_id
    return None


async def resolve_target(event, args, allow_chat):
    """آیدی هدف: آرگومان > ریپلای > پیوی (و برای اسپم: همین چت). برمی‌گردونه (آیدی, پیام خطا)"""
    if args:
        try:
            return int(args[0]), None
        except ValueError:
            return None, "__آیدی عددی وارد شده نامعتبر است!__"
    rid = await reply_target_id(event)
    if rid is not None:
        return rid, None
    if event.is_private:
        return event.chat_id, None
    if allow_chat:
        return event.chat_id, None
    return None, "__لطفا در پیوی شخص ارسال کنید، روی او ریپلای کنید یا آیدی عددی را جلوی دستور بنویسید!__"


def show_list(title, items):
    if not items:
        return f"__لیست {title} خالی است!__"
    body = "\n".join(f"{i}. `{x}`" for i, x in enumerate(items, start=1))
    return f"__🔰 لیست {title} بصورت زیر است:\n(برای کپی کردن روی آن کلیک کنید)__\n\n{body}"


async def list_add(acc, event, key, title, given_id, after=None):
    if given_id in acc.cfg[key]:
        await acc.say(event, f"__آیدی موردنظر در لیست {title} بوده است!__")
        return
    acc.cfg[key].append(given_id)
    acc.save()
    if after:
        after()
    await acc.say(event, f"__آیدی `{given_id}` با موفقیت به لیست {title} اضافه شد!__")


async def list_del(acc, event, key, title, given_id, after=None):
    if given_id not in acc.cfg[key]:
        await acc.say(event, f"__آیدی موردنظر در لیست {title} نبوده است!__")
        return
    acc.cfg[key].remove(given_id)
    acc.save()
    if after:
        after()
    await acc.say(event, f"__آیدی `{given_id}` با موفقیت از لیست {title} حذف شد!__")


def _onoff(args):
    if len(args) != 1:
        return None
    v = args[0].lower()
    return True if v == "on" else False if v == "off" else None


# ================== دستورها ==================
async def cmd_ping(acc, event, args, raw):
    await acc.say(event, f"__🌲{acc.name} is online🌲__")


async def cmd_help(acc, event, args, raw):
    await acc.say(event, HELP_TEXT)


async def cmd_bot(acc, event, args, raw):
    v = _onoff(args)
    if v is None:
        return
    if v:
        txt = "__ربات روشن بوده است!__" if not acc.is_off else "__ربات روشن شد!__"
        acc.is_off = False
    else:
        txt = "__ربات خاموش بوده است!__" if acc.is_off else "__ربات خاموش شد!__"
        acc.is_off = True
    await acc.say(event, txt)


async def cmd_settime(acc, event, args, raw):
    try:
        n = int(args[0])
    except (IndexError, ValueError):
        return
    if n < 1:
        await acc.say(event, "__مقدار ورودی نامعتبر است!__")
        return
    acc.cfg["spam_time"] = n
    acc.save()
    eff = max(MIN_SPAM_INTERVAL, n)
    extra = f" (حداقل مجاز {MIN_SPAM_INTERVAL} ثانیه است)" if eff != n else ""
    await acc.say(event, f"__تاخیر بین هر اسپم به {eff} ثانیه تغییر یافت!__{extra}")


async def cmd_id(acc, event, args, raw):
    rid = await reply_target_id(event)
    if rid is not None:
        await acc.say(event, f"__آیدی عددی کاربر ریپلای شده  :  `{rid}`__")
    elif event.is_private:
        await acc.say(event, f"__آیدی عددی این کاربر  :  `{event.chat_id}`__")
    else:
        await acc.say(event, f"__آیدی عددی این گروه  :  `{event.chat_id}`__")


async def cmd_reply(acc, event, args, raw):
    v = _onoff(args)
    if v is None:
        return
    cur = bool(acc.cfg["enemy_reply"])
    if v:
        txt = "__ریپلای روشن بوده است!__" if cur else "__ریپلای روشن شد!__"
    else:
        txt = "__ریپلای خاموش شد!__" if cur else "__ریپلای خاموش بوده است!__"
    acc.cfg["enemy_reply"] = 1 if v else 0
    acc.save()
    await acc.say(event, txt)


async def cmd_typing(acc, event, args, raw):
    v = _onoff(args)
    if v is None:
        return
    cid = event.chat_id
    if v:
        txt = ("__حالت تایپینگ در اینجا روشن بوده است!__" if cid in acc.typing_ids
               else "__حالت تایپینگ در اینجا روشن شد!__")
        acc.typing_ids.add(cid)
        acc.ensure_task("typing", acc.typing_loop)
    else:
        txt = ("__حالت تایپینگ در اینجا خاموش شد!__" if cid in acc.typing_ids
               else "__حالت تایپینگ در اینجا خاموش بوده است!__")
        acc.typing_ids.discard(cid)
        if not acc.typing_ids:
            acc.stop_task("typing")
    await acc.say(event, txt)


# ---------- فحش (مشترک) ----------
async def cmd_addfosh(acc, event, args, raw):
    msg = await event.get_reply_message() if event.is_reply else None
    text = (getattr(msg, "text", None) or "").strip()
    if not text:
        return
    if text in shared["fosh_list"]:
        await acc.say(event, "__متن ریپلای شده در لیست فحش ها بوده است!__")
        return
    shared["fosh_list"].append(text)
    save_shared()
    await acc.say(event, "__متن ریپلای شده به لیست فحش ها (مشترک همه‌ی اکانت‌ها) اضافه شد!__")


async def cmd_addallfosh(acc, event, args, raw):
    msg = await event.get_reply_message() if event.is_reply else None
    text = getattr(msg, "text", None) or ""
    added = 0
    for line in text.split("\n"):
        line = line.strip()
        if line and line not in shared["fosh_list"]:
            shared["fosh_list"].append(line)
            added += 1
    save_shared()
    await acc.say(event, f"__{added} مورد به لیست فحش ها (مشترک) اضافه شد!__")


async def cmd_delfosh(acc, event, args, raw):
    msg = await event.get_reply_message() if event.is_reply else None
    text = (getattr(msg, "text", None) or "").strip()
    if not text:
        return
    if text in shared["fosh_list"]:
        shared["fosh_list"].remove(text)
        save_shared()
        await acc.say(event, "__متن ریپلای شده از لیست فحش ها (مشترک) حذف شد!__")
    else:
        await acc.say(event, "__متن ریپلای شده در لیست فحش ها نبوده است!__")


async def cmd_flist(acc, event, args, raw):
    await acc.say(event, show_list("فحش ها (مشترک)", shared["fosh_list"]))


async def cmd_cleanflist(acc, event, args, raw):
    shared["fosh_list"].clear()
    save_shared()
    await acc.say(event, "__لیست فحش ها (برای همه‌ی اکانت‌ها) خالی شد!__")


async def cmd_restart(acc, event, args, raw):
    was_clock = acc.cfg.get("clock_on")
    acc.cfg.clear()
    acc.cfg.update(copy.deepcopy(DEFAULT_CONFIG))
    acc.save()
    acc.typing_ids.clear()
    acc.stop_all()
    if was_clock:
        await acc.restore_name()
    acc.is_off = False
    await acc.say(event, "__تنظیمات این اکانت ریستارت شد! (لیست فحش مشترک دست‌نخورده موند)__")


# ---------- دشمن ----------
async def cmd_setenemy(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=False)
    if err:
        await acc.say(event, err)
        return
    await list_add(acc, event, "enemy_list", "دشمن", gid)


async def cmd_delenemy(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=False)
    if err:
        await acc.say(event, err)
        return
    await list_del(acc, event, "enemy_list", "دشمن", gid)


async def cmd_enemylist(acc, event, args, raw):
    await acc.say(event, show_list("دشمن ها", acc.cfg["enemy_list"]))


async def cmd_cleanenemy(acc, event, args, raw):
    acc.cfg["enemy_list"] = []
    acc.save()
    await acc.say(event, "__لیست دشمن ها با موفقیت خالی شد!__")


# ---------- سکوت ----------
async def cmd_add(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=False)
    if err:
        await acc.say(event, err)
        return
    await list_add(acc, event, "silence_list", "سکوت", gid)


async def cmd_del(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=False)
    if err:
        await acc.say(event, err)
        return
    await list_del(acc, event, "silence_list", "سکوت", gid)


async def cmd_dellist(acc, event, args, raw):
    await acc.say(event, show_list("سکوت", acc.cfg["silence_list"]))


# ---------- اسپم ----------
async def cmd_setspam(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=True)
    if err:
        await acc.say(event, err)
        return
    await list_add(acc, event, "spam_list", "اسپم", gid,
                   after=lambda: acc.ensure_task("spam", acc.spam_loop))


async def cmd_spamlist(acc, event, args, raw):
    await acc.say(event, show_list("اسپم", acc.cfg["spam_list"]))


async def cmd_cleanslist(acc, event, args, raw):
    acc.cfg["spam_list"] = []
    acc.save()
    acc.stop_task("spam")
    await acc.say(event, "__لیست اسپم با موفقیت خالی شد!__")


async def cmd_settext(acc, event, args, raw):
    if event.is_reply:
        msg = await event.get_reply_message()
        try:
            snd = await msg.get_sender()
            name = getattr(snd, "first_name", None) or getattr(snd, "username", None) or "کاربر"
            acc.cfg["intro_text"] = f"[{name}](tg://user?id={msg.sender_id})  "
        except Exception:
            await acc.say(event, "__نتونستم کاربر ریپلای شده رو پیدا کنم!__")
            return
        acc.save()
        await acc.say(event, "__متن پیشفرض به تگ کردن کاربر ریپلای شده تغییر یافت!__")
        return
    parts = raw.split(None, 1)
    acc.cfg["intro_text"] = parts[1] if len(parts) > 1 else ""
    acc.save()
    await acc.say(event, "__متن پیشفرض با موفقیت تغییر یافت!__")


async def cmd_deltext(acc, event, args, raw):
    acc.cfg["intro_text"] = ""
    acc.save()
    await acc.say(event, "__متن پیشفرض با موفقیت حذف شد!__")


async def cmd_name(acc, event, args, raw):
    msg = await event.get_reply_message() if event.is_reply else None
    text = (getattr(msg, "text", None) or "").strip()
    if not text:
        await acc.say(event, "__روی یه متن ریپلای کن!__")
        return
    try:
        from splusthon.tl.functions.account import UpdateProfileRequest
        await acc.client(UpdateProfileRequest(first_name=text[:64]))
        await acc.say(event, f"__نام اکانت به «{text[:64]}» تغییر کرد__")
    except Exception as e:
        log(f"[{acc.name}] خطا در تغییر نام: {e!r}")
        await acc.say(event, "__تغییر نام در این نسخه‌ی کتابخونه یا سروش پشتیبانی نمی‌شه__")


# ---------- تایمر ----------
async def cmd_timer(acc, event, args, raw):
    v = _onoff(args)
    if v is None:
        await acc.say(event, "__دستور به شکل نادرست وارد شده است__")
        return
    acc.cfg["timer_on"] = v
    acc.save()
    if v:
        acc.ensure_task("timer", acc.timer_loop)
        await acc.say(event, "__تایمر روشن شد__")
    else:
        acc.stop_task("timer")
        await acc.say(event, "__تایمر خاموش شد__")


async def cmd_pingtimer(acc, event, args, raw):
    if acc.cfg["timer_on"]:
        await acc.say(event, f"__تایمر روشن است\n\nزمان {acc.cfg['timer_minutes']} دقیقه__")
    else:
        await acc.say(event, "__تایمر خاموش است__")


async def cmd_timertext(acc, event, args, raw):
    msg = await event.get_reply_message() if event.is_reply else None
    text = (getattr(msg, "text", None) or "").strip()
    if not text:
        await acc.say(event, "__روی یه متن ریپلای کن!__")
        return
    acc.cfg["timer_text"] = text
    acc.save()
    await acc.say(event, f"__متن تایمر با موفقیت انتخاب شد__\n\n{text}")


async def cmd_settimer(acc, event, args, raw):
    try:
        n = int(args[0])
        if n < 1:
            raise ValueError
    except (IndexError, ValueError):
        await acc.say(event, "__دستور به شکل صحیح وارد نشده\n\n/settimer عدد(دقیقه)__")
        return
    acc.cfg["timer_minutes"] = n
    acc.save()
    await acc.say(event, f"__زمان تایمر {n} دقیقه شد__")


async def cmd_setspamtimer(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=True)
    if err:
        await acc.say(event, err)
        return
    await list_add(acc, event, "timer_spam_list", "اسپم تایمر", gid)


async def cmd_listspamtimer(acc, event, args, raw):
    await acc.say(event, show_list("اسپم تایمر", acc.cfg["timer_spam_list"]))


async def cmd_deltimerspam(acc, event, args, raw):
    gid, err = await resolve_target(event, args, allow_chat=False)
    if err:
        await acc.say(event, err)
        return
    await list_del(acc, event, "timer_spam_list", "اسپم تایمر", gid)


async def cmd_cleanlisttimer(acc, event, args, raw):
    acc.cfg["timer_spam_list"] = []
    acc.save()
    await acc.say(event, "__لیست اسپم تایمر با موفقیت خالی شد!__")


# ---------- ساعت کنار اسم ----------
async def cmd_clock(acc, event, args, raw):
    v = _onoff(args)
    if v is None:
        await acc.say(event, "__دستور به شکل نادرست وارد شده است: /clock on|off__")
        return
    if v:
        acc.cfg["clock_on"] = True
        acc.save()
        acc.stop_task("clock")
        acc.ensure_task("clock", acc.clock_loop)
        await acc.say(event, "__ساعت کنار اسم روشن شد__")
    else:
        acc.cfg["clock_on"] = False
        acc.save()
        acc.stop_task("clock")
        await acc.restore_name()
        await acc.say(event, "__ساعت کنار اسم خاموش شد و اسم اصلی برگشت__")


COMMANDS = {
    "clock": cmd_clock,
    "ping": cmd_ping, "help": cmd_help, "bot": cmd_bot, "settime": cmd_settime,
    "id": cmd_id, "reply": cmd_reply, "typing": cmd_typing,
    "addfosh": cmd_addfosh, "addallfosh": cmd_addallfosh, "delfosh": cmd_delfosh,
    "flist": cmd_flist, "cleanflist": cmd_cleanflist, "restart": cmd_restart,
    "setenemy": cmd_setenemy, "delenemy": cmd_delenemy, "enemylist": cmd_enemylist,
    "cleanlist": cmd_cleanenemy, "cleanelist": cmd_cleanenemy,
    "add": cmd_add, "del": cmd_del, "dellist": cmd_dellist,
    "setspam": cmd_setspam, "spamlist": cmd_spamlist, "cleanslist": cmd_cleanslist,
    "settext": cmd_settext, "deltext": cmd_deltext, "name": cmd_name,
    "timer": cmd_timer, "pingtimer": cmd_pingtimer, "timertext": cmd_timertext,
    "settimer": cmd_settimer, "setspamtimer": cmd_setspamtimer,
    "listspamtimer": cmd_listspamtimer, "deltimerspam": cmd_deltimerspam,
    "cleanlisttimer": cmd_cleanlisttimer,
}


# ================== حلقه‌ی asyncio در یک ترد جدا ==================
_loop = None
_loop_lock = threading.Lock()
_state = {"running": False}
_tasks = {}     # name -> asyncio.Task
_accs = {}      # name -> Account
_login = {"client": None, "phone": None, "hash": None}


def _on_loop_exc(loop, ctx):
    exc = ctx.get("exception")
    if exc is not None and not isinstance(exc, asyncio.CancelledError):
        log(f"خطای پس‌زمینه: {exc!r}")


def _ensure_loop():
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            _loop.set_exception_handler(_on_loop_exc)
            threading.Thread(target=_loop.run_forever, daemon=True, name="bot-loop").start()
        return _loop


def _run(coro, timeout=90):
    """اجرای یک coroutine روی حلقه‌ی ربات و صبر برای جواب (از ترد Kotlin صدا زده می‌شه)"""
    fut = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    return fut.result(timeout)


# ================== ورود با شماره و کد ==================
async def _send_code(phone):
    old = _login.get("client")
    if old is not None:
        try:
            await old.disconnect()
        except Exception:
            pass
    client = SoroushClient(StringSession())
    await client.connect()
    sent = await client.send_code_request(phone)
    _login.update(client=client, phone=phone, hash=getattr(sent, "phone_code_hash", None))
    log(f"کد ورود برای {phone} ارسال شد.")


async def _finish_login():
    client = _login["client"]
    phone = _login["phone"]
    session = client.session.save()
    label = ""
    try:
        me = await client.get_me()
        label = getattr(me, "first_name", "") or ""
    except Exception:
        pass
    try:
        await client.disconnect()
    except Exception:
        pass
    _login.update(client=None, phone=None, hash=None)

    specs = _read_json(ACC_FILE, [])
    spec = None
    for s in specs:
        if s.get("phone") == phone:
            s["session"] = session
            s["label"] = label
            spec = s
            break
    if spec is None:
        used = {s.get("name") for s in specs}
        i = 1
        while f"acc{i}" in used:
            i += 1
        spec = {"name": f"acc{i}", "phone": phone, "label": label, "session": session}
        specs.append(spec)
    _write_json(ACC_FILE, specs)
    log(f"✅ اکانت {spec['name']} ({phone}) ذخیره شد.")
    if _state["running"]:
        _launch(spec, force=True)
    return "OK"


async def _sign_in_code(code):
    client = _login.get("client")
    if client is None:
        raise RuntimeError("اول شماره رو وارد کن و کد بگیر")
    try:
        await client.sign_in(_login["phone"], code, phone_code_hash=_login["hash"])
    except Exception as e:
        if type(e).__name__ == "SessionPasswordNeededError":
            return "PASSWORD"
        raise
    return await _finish_login()


async def _sign_in_password(password):
    client = _login.get("client")
    if client is None:
        raise RuntimeError("اول شماره رو وارد کن و کد بگیر")
    await client.sign_in(password=password)
    return await _finish_login()


def send_code(phone):
    _run(_send_code(phone))
    return "OK"


def sign_in_code(code):
    return _run(_sign_in_code(str(code).strip()))


def sign_in_password(password):
    return _run(_sign_in_password(str(password)))


# ================== روشن / خاموش ==================
async def _run_account(spec):
    name = spec["name"]
    try:
        acc = Account(spec)
    except Exception as e:
        log(f"[{name}] ساخت کلاینت نشد: {e!r}")
        return
    _accs[name] = acc
    delay = 15
    try:
        while _state["running"]:
            try:
                log(f"[{name}] در حال اتصال به سروش...")
                await acc.client.connect()
                if not await acc.client.is_user_authorized():
                    log(f"[{name}] سشن منقضی شده؛ از بخش «اکانت‌ها» دوباره وارد شو.")
                    return
                me = await acc.client.get_me()
                acc.connected = True
                log(f"✅ [{name}] روشن شد → id={getattr(me, 'id', '?')} | {getattr(me, 'first_name', '?')}")
                acc.start_background()
                delay = 15
                await acc.client.run_until_disconnected()
                log(f"[{name}] ارتباط قطع شد.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log(f"[{name}] خطا ({type(e).__name__}): {e}")
            finally:
                acc.connected = False
                acc.stop_all()
                acc.save()
            if not _state["running"]:
                break
            log(f"[{name}] {delay} ثانیه دیگه دوباره وصل می‌شم...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)
    finally:
        acc.connected = False
        try:
            await acc.client.disconnect()
        except (Exception, asyncio.CancelledError):
            pass
        if _accs.get(name) is acc:
            _accs.pop(name, None)


def _launch(spec, force=False):
    name = spec["name"]
    old = _tasks.get(name)
    if old is not None and not old.done():
        if not force:
            return
        old.cancel()
    _tasks[name] = asyncio.ensure_future(_run_account(spec))


async def _start_all():
    _state["running"] = True
    for spec in _read_json(ACC_FILE, []):
        _launch(spec)
    log("ربات روشن شد.")


async def _stop_all():
    _state["running"] = False
    tasks = list(_tasks.values())
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _tasks.clear()
    log("ربات خاموش شد.")


async def _remove_account(name):
    t = _tasks.pop(name, None)
    if t is not None:
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
    specs = [s for s in _read_json(ACC_FILE, []) if s.get("name") != name]
    _write_json(ACC_FILE, specs)
    try:
        os.remove(os.path.join(DATA_DIR, f"cfg_{name}.json"))
    except OSError:
        pass
    log(f"اکانت {name} حذف شد.")


def start_bot():
    asyncio.run_coroutine_threadsafe(_start_all(), _ensure_loop())
    return "OK"


def stop_bot():
    _run(_stop_all(), timeout=30)
    return "OK"


def remove_account(name):
    _run(_remove_account(str(name)), timeout=30)
    return "OK"


def status():
    specs = _read_json(ACC_FILE, [])
    accounts = []
    for s in specs:
        acc = _accs.get(s.get("name"))
        accounts.append({
            "name": s.get("name", "?"),
            "phone": s.get("phone", ""),
            "label": s.get("label", ""),
            "connected": bool(acc and acc.connected),
        })
    return json.dumps({
        "running": _state["running"],
        "accounts": accounts,
        "log": "\n".join(list(LOG)[-25:]),
    }, ensure_ascii=False)
