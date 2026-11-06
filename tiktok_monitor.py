"""
Pemantau TikTok untuk BalikLayar AI.

- Deteksi LIVE akun TikTok (via yt-dlp) -> kirim notifikasi ke channel read-only.
- Deteksi VIDEO BARU (via RSS feed, mis. RSSHub) -> kirim notifikasi ke channel yang sama.
- Channel read-only dibuat otomatis oleh bot (member hanya bisa membaca).

Konfigurasi lewat environment variable (lihat config.py):
  TIKTOK_USERNAME, TIKTOK_VIDEO_FEED_URL, TIKTOK_POLL_SECONDS
"""

import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET

import discord
import httpx
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
        print(f"❌ Gagal menyimpan tiktok_state.json: {e}")


async def check_live() -> bool | None:
    """True = sedang live, False = tidak live, None = gagal cek."""
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--skip-download", "--no-warnings", "-J", LIVE_URL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    if proc.returncode == 0 and out:
        return True
    if b"not currently live" in err:
        return False
    print(f"⚠️ TikTok live check gagal: {err.decode(errors='ignore')[:200]}")
    return None


async def fetch_latest_videos() -> list[dict]:
    """Ambil daftar video terbaru dari RSS feed. Return list {id, title, url} (terbaru dulu)."""
    feed = config.TIKTOK_VIDEO_FEED_URL
    if not feed:
        return []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(feed, headers={"User-Agent": "BalikLayarBot/1.0 (+discord)"})
            r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as e:
        print(f"⚠️ Gagal ambil feed video TikTok: {e}")
        return []

    videos = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        m = re.search(r"/video/(\d+)", link)
        vid = m.group(1) if m else (item.findtext("guid") or link)
        title = re.sub(r"<[^>]+>", "", item.findtext("title") or "").strip()
        if vid and link:
            videos.append({"id": vid, "title": title, "url": link})
    return videos


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
                topic=f"Notifikasi otomatis LIVE & video baru TikTok @{config.TIKTOK_USERNAME} (read-only)",
                reason="Channel read-only notifikasi TikTok",
            )
        except Exception as e:
            print(f"❌ Gagal membuat channel TikTok: {e}")
            return None
        self.state["channel_id"] = ch.id
        _save_state(self.state)
        print(f"✅ Channel TikTok dibuat: #{ch.name} ({ch.id})")
        return ch

    async def _tick(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        ch = await self.ensure_channel(guild)
        if not ch:
            return

        await self._check_live(ch)
        await self._check_videos(ch)

    async def _check_live(self, ch: discord.TextChannel):
        live = await check_live()
        if live is None:
            return
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

    async def _check_videos(self, ch: discord.TextChannel):
        videos = await fetch_latest_videos()
        if not videos:
            return
        seen = set(self.state.get("seen_videos", []))
        if not seen:
            # Run pertama: tandai semua video lama sebagai sudah dilihat agar tidak spam.
            self.state["seen_videos"] = [v["id"] for v in videos][:50]
            _save_state(self.state)
            return

        new = [v for v in videos if v["id"] not in seen]
        for v in reversed(new):  # kirim dari yang paling lama
            embed = discord.Embed(
                title=f"🎬 Video baru dari @{config.TIKTOK_USERNAME}",
                description=v["title"][:300] or "Video baru telah diposting!",
                url=v["url"],
                color=0x00F2EA,
            )
            await ch.send(v["url"], embed=embed)
            seen.add(v["id"])
        if new:
            self.state["seen_videos"] = list(seen)[-100:]
            _save_state(self.state)
