"""
Pemantau TikTok untuk BalikLayar AI.

- Deteksi LIVE akun TikTok (via yt-dlp) -> kirim notifikasi ke channel read-only.
- Channel read-only dibuat otomatis oleh bot (member hanya bisa membaca).

Konfigurasi lewat environment variable (lihat config.py):
  TIKTOK_USERNAME, TIKTOK_POLL_SECONDS
"""

import asyncio
import json
import os
import sys

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
        print(f"❌ Gagal menyimpan tiktok_state.json: {e}")


async def check_live() -> bool | None:
    """True = sedang live, False = tidak live, None = gagal cek."""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "yt_dlp", "--skip-download", "--no-warnings", "-J", LIVE_URL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        print(f"⚠️ Tidak bisa menjalankan yt-dlp (pip install yt-dlp?): {e}")
        return None
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

        for check in (self._check_live,):
            try:
                await check(ch)
            except Exception as e:  # jangan sampai satu error mematikan loop
                print(f"⚠️ TikTok monitor {check.__name__} error: {e}")

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
