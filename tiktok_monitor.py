"""
Pemantau TikTok untuk BalikLayar AI.

- Deteksi LIVE akun TikTok (HTTP biasa, tanpa yt-dlp) -> kirim notifikasi ke channel read-only.
  Cara cek sama dengan tiktok-live-connector (dipakai Patungan Yuk!):
  1) scrape SIGI_STATE di halaman /@user/live, 2) fallback ke api-live/user/room.
  liveRoom.status != 4 berarti sedang live.
- Channel read-only dibuat otomatis oleh bot (member hanya bisa membaca).

Konfigurasi lewat environment variable (lihat config.py):
  TIKTOK_USERNAME, TIKTOK_POLL_SECONDS
"""

import asyncio
import json
import os
import re

import aiohttp

import discord
from discord.ext import tasks

import config

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_state.json")
PROFILE_URL = f"https://www.tiktok.com/@{config.TIKTOK_USERNAME}"
LIVE_URL = f"{PROFILE_URL}/live"


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Gagal menyimpan tiktok_state.json: {e}", flush=True)


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tiktok.com/",
}
_SIGI_RE = re.compile(r'<script id="SIGI_STATE" type="application/json">(.*?)</script>', re.S)
LAST_ERROR = ""
_STATUS_OFFLINE = 4  # liveRoom.status: 2 = live, 4 = offline (sama seperti tiktok-live-connector)


async def _status_from_html(session: aiohttp.ClientSession) -> int | None:
    async with session.get(LIVE_URL) as r:
        html = await r.text()
    m = _SIGI_RE.search(html)
    if not m:
        raise ValueError(f"SIGI_STATE tidak ada (HTTP {r.status}, mungkin diblok/captcha)")
    info = (json.loads(m.group(1)).get("LiveRoom") or {}).get("liveRoomUserInfo") or {}
    return (info.get("liveRoom") or {}).get("status")


async def _status_from_api(session: aiohttp.ClientSession) -> int | None:
    params = {"aid": "1988", "sourceType": "54", "uniqueId": config.TIKTOK_USERNAME}
    async with session.get("https://www.tiktok.com/api-live/user/room/", params=params) as r:
        data = await r.json(content_type=None)
    if data.get("statusCode"):
        raise ValueError(f"API error {data.get('statusCode')} {data.get('message', '')}")
    return ((data.get("data") or {}).get("liveRoom") or {}).get("status")


async def check_live() -> bool | None:
    """True = sedang live, False = tidak live, None = gagal cek."""
    errors = []
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
        for source in (_status_from_html, _status_from_api):
            try:
                status = await source(session)
                if status is not None:
                    return status != _STATUS_OFFLINE
                errors.append(f"{source.__name__}: status kosong")
            except Exception as e:
                errors.append(f"{source.__name__}: {e}")
    global LAST_ERROR
    LAST_ERROR = " | ".join(errors)[:300]
    print(f"⚠️ TikTok live check gagal: {LAST_ERROR}", flush=True)
    return None


class TikTokMonitor:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.state = _load_state()
        self.loop_task = tasks.loop(seconds=config.TIKTOK_POLL_SECONDS)(self._tick)
        self.loop_task.before_loop(self._before)

    def start(self):
        if not self.loop_task.is_running():
            self.loop_task.start()

    async def _before(self):
        await self.bot.wait_until_ready()

    async def ensure_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cid = config.CHANNEL_TIKTOK or self.state.get("channel_id")
        ch = guild.get_channel(cid) if cid else None
        if isinstance(ch, discord.TextChannel):
            return ch

        # Buat channel read-only: @everyone bisa lihat & baca, tapi tidak bisa kirim/thread/reaksi.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
                add_reactions=False,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, embed_links=True, manage_channels=True,
            ),
        }
        unverified = guild.get_role(config.ROLE_UNVERIFIED)
        if unverified:  # Unverified hanya boleh lihat channel info, termasuk ini
            overwrites[unverified] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)

        category = None
        announce = guild.get_channel(config.CHANNEL_ANNOUNCEMENT)
        if announce:
            category = announce.category
        try:
            ch = await guild.create_text_channel(
                "┃・🎬・tiktok-alfiqo",
                overwrites=overwrites,
                category=category,
                topic=f"Notifikasi otomatis LIVE TikTok @{config.TIKTOK_USERNAME} (read-only)",
                reason="Channel read-only notifikasi TikTok",
            )
        except Exception as e:
            print(f"❌ Gagal membuat channel TikTok: {e}", flush=True)
            return None
        self.state["channel_id"] = ch.id
        _save_state(self.state)
        print(f"✅ Channel TikTok dibuat: #{ch.name} ({ch.id})", flush=True)
        return ch

    async def _tick(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        ch = await self.ensure_channel(guild)
        if not ch:
            return

        for check in (self._check_live,):
            try:
                await check(ch)
            except Exception as e:  # jangan sampai satu error mematikan loop
                print(f"⚠️ TikTok monitor {check.__name__} error: {e}", flush=True)

    async def _report(self, live: bool | None):
        """Kirim status cek ke #bot-logs saat pertama kali jalan & tiap kali hasilnya berubah (ok <-> gagal)."""
        outcome = "fail" if live is None else "ok"
        if outcome == getattr(self, "last_outcome", None):
            return
        self.last_outcome = outcome
        if live is None:
            msg = f"⚠️ TikTok live check @{config.TIKTOK_USERNAME} GAGAL: `{LAST_ERROR}`"
        else:
            msg = f"✅ TikTok live check @{config.TIKTOK_USERNAME} jalan: {'🔴 sedang LIVE' if live else 'tidak live'}"
        print(msg, flush=True)
        logs = self.bot.get_channel(config.CHANNEL_LOGS)
        if logs:
            try:
                await logs.send(msg)
            except Exception as e:
                print(f"⚠️ Gagal kirim ke bot-logs: {e}", flush=True)

    async def _check_live(self, ch: discord.TextChannel):
        live = await check_live()
        await self._report(live)
        if live is None:
            # Kalau cek gagal terus (~30 menit), anggap tidak live agar live berikutnya tetap dinotif
            # (mencegah is_live nyangkut True selamanya).
            self.fail_count = getattr(self, "fail_count", 0) + 1
            if self.fail_count * config.TIKTOK_POLL_SECONDS >= 1800 and self.state.get("is_live"):
                self.state["is_live"] = False
                _save_state(self.state)
            return
        self.fail_count = 0
        was_live = self.state.get("is_live", False)
        if live and not was_live:
            embed = discord.Embed(
                title=f"🔴 @{config.TIKTOK_USERNAME} sedang LIVE di TikTok!",
                description=f"Gabung sekarang: {LIVE_URL}",
                url=LIVE_URL,
                color=0xFF0050,
            )
            await ch.send("@everyone" if config.TIKTOK_PING_EVERYONE else None, embed=embed,
                          allowed_mentions=discord.AllowedMentions(everyone=config.TIKTOK_PING_EVERYONE))
        if live != was_live:
            self.state["is_live"] = live
            _save_state(self.state)
