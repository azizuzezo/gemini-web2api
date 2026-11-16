"""
Pemantau TikTok untuk BalikLayar AI (tanpa yt-dlp, HTTP biasa).

Untuk setiap akun di config.TIKTOK_USERNAMES:
- LIVE: cara cek sama dengan tiktok-live-connector (dipakai Patungan Yuk!):
  1) scrape SIGI_STATE di halaman /@user/live, 2) fallback ke api-live/user/room.
  liveRoom.status != 4 berarti sedang live.
- Semua notif dikirim ke satu channel read-only (dibuat otomatis kalau belum ada).
- Status cek (berhasil/gagal) dilaporkan ke #bot-logs setiap kali berubah.

Konfigurasi lewat environment variable (lihat config.py):
  TIKTOK_USERNAMES, TIKTOK_POLL_SECONDS, TIKTOK_PING_EVERYONE
"""

import json
import os
import re

import aiohttp

import discord
from discord.ext import tasks

import config

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_state.json")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://www.tiktok.com/",
}
_SIGI_RE = re.compile(r'<script id="SIGI_STATE" type="application/json">(.*?)</script>', re.S)
_STATUS_OFFLINE = 4  # liveRoom.status: 2 = live, 4 = offline (sama seperti tiktok-live-connector)
TIKTOK_PINK = 0xFE2C55

NOTIF_VERSION = 3  # naikkan kalau tampilan notif live diubah -> live yang sedang jalan dikirim ulang sekali

LAST_ERROR = ""  # alasan gagal terakhir (dipakai laporan #bot-logs)


def profile_url(username: str) -> str:
    return f"https://www.tiktok.com/@{username}"


def live_url(username: str) -> str:
    return f"{profile_url(username)}/live"


# ------------------------------------------------------------------ state

def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    # Migrasi format lama (satu akun, field di root) -> per akun
    if "accounts" not in state:
        legacy = {k: state.pop(k) for k in ("is_live", "notif_version", "last_message_id") if k in state}
        state["accounts"] = {config.TIKTOK_USERNAMES[0]: legacy} if legacy else {}
    for acc in state["accounts"].values():  # sisa fitur video baru (sudah dihapus)
        for k in ("last_video_id", "video_count"):
            acc.pop(k, None)
    return state


def _save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Gagal menyimpan tiktok_state.json: {e}", flush=True)


# ------------------------------------------------------------------ live

async def _live_info_from_html(session: aiohttp.ClientSession, username: str) -> dict:
    async with session.get(live_url(username)) as r:
        html = await r.text()
    m = _SIGI_RE.search(html)
    if not m:
        raise ValueError(f"SIGI_STATE tidak ada (HTTP {r.status}, mungkin diblok/captcha)")
    return (json.loads(m.group(1)).get("LiveRoom") or {}).get("liveRoomUserInfo") or {}


async def _live_info_from_api(session: aiohttp.ClientSession, username: str) -> dict:
    params = {"aid": "1988", "sourceType": "54", "uniqueId": username}
    async with session.get("https://www.tiktok.com/api-live/user/room/", params=params) as r:
        data = await r.json(content_type=None)
    if data.get("statusCode"):
        raise ValueError(f"API error {data.get('statusCode')} {data.get('message', '')}")
    return data.get("data") or {}


async def fetch_live(session: aiohttp.ClientSession, username: str) -> tuple[bool | None, dict]:
    """(True/False/None, info). info = liveRoomUserInfo: {user: {...}, liveRoom: {...}}."""
    global LAST_ERROR
    errors = []
    for source in (_live_info_from_html, _live_info_from_api):
        try:
            info = await source(session, username)
            status = (info.get("liveRoom") or {}).get("status")
            if status is not None:
                return status != _STATUS_OFFLINE, info
            errors.append(f"{source.__name__}: status kosong")
        except Exception as e:
            errors.append(f"{source.__name__}: {e}")
    LAST_ERROR = " | ".join(errors)[:300]
    print(f"⚠️ TikTok live check @{username} gagal: {LAST_ERROR}", flush=True)
    return None, {}


async def check_live(username: str | None = None) -> bool | None:
    """Helper untuk tes manual: True = live, False = tidak live, None = gagal."""
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as s:
        return (await fetch_live(s, username or config.TIKTOK_USERNAMES[0]))[0]


def build_live_message(username: str, info: dict) -> tuple[str, discord.Embed, discord.ui.View]:
    user = info.get("user") or {}
    room = info.get("liveRoom") or {}
    stats = room.get("liveRoomStats") or {}
    nickname = user.get("nickname") or username
    avatar = user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")
    room_title = (room.get("title") or "").strip()
    cover = room.get("coverUrl") or room.get("squareCoverImg")
    viewers = stats.get("userCount")
    started = room.get("startTime")
    url = live_url(username)

    content = (
        f"🔴 **{nickname} lagi live sekarang!**\n"
        f"Yuk mampir, ngobrol bareng & tanya-tanya langsung soal konten AI dan affiliate 👇"
    )
    embed = discord.Embed(
        title=f"🎥 {room_title}" if room_title else "🎥 Lagi live di TikTok, gas gabung!",
        url=url,
        description=(
            "Selagi masih live, ini kesempatan buat:\n"
            "💬 tanya langsung & dapat jawaban real-time\n"
            "💡 intip strategi & tools yang lagi dipakai\n"
            "🤝 kenalan sama sesama kreator BalikLayar\n\n"
            f"**[👉 Klik di sini buat masuk live]({url})**"
        ),
        color=TIKTOK_PINK,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_author(name=f"{nickname} (@{username})", url=profile_url(username), icon_url=avatar or None)
    if avatar:
        embed.set_thumbnail(url=avatar)
    if cover:
        embed.set_image(url=cover)
    if viewers:
        embed.add_field(name="👀 Lagi nonton", value=f"**{viewers:,}** orang".replace(",", "."), inline=True)
    if started:
        embed.add_field(name="⏱️ Mulai live", value=f"<t:{int(started)}:R>", inline=True)
    embed.set_footer(text="BalikLayar AI • notifikasi live otomatis")

    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Tonton live sekarang", emoji="🔴", url=url))
    view.add_item(discord.ui.Button(label="Follow TikTok", emoji="➕", url=profile_url(username)))
    if config.TIKTOK_PING_EVERYONE:
        content = "@everyone " + content
    return content, embed, view


# ------------------------------------------------------------------ monitor

class TikTokMonitor:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.state = _load_state()
        self.outcomes: dict[str, str] = {}   # "user:kind" -> "ok"/"fail" (untuk laporan #bot-logs)
        self.fail_counts: dict[str, int] = {}
        self.loop_task = tasks.loop(seconds=config.TIKTOK_POLL_SECONDS)(self._tick)
        self.loop_task.before_loop(self._before)

    def start(self):
        if not self.loop_task.is_running():
            self.loop_task.start()

    async def _before(self):
        await self.bot.wait_until_ready()

    def _acc(self, username: str) -> dict:
        return self.state.setdefault("accounts", {}).setdefault(username, {})

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
                mention_everyone=True,
            ),
        }
        unverified = guild.get_role(config.ROLE_UNVERIFIED)
        if unverified:  # Unverified hanya boleh lihat channel info, termasuk ini
            overwrites[unverified] = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)

        category = None
        announce = guild.get_channel(config.CHANNEL_ANNOUNCEMENT)
        if announce:
            category = announce.category
        accounts = ", ".join(f"@{u}" for u in config.TIKTOK_USERNAMES)
        try:
            ch = await guild.create_text_channel(
                "┃・🎬・tiktok-live",
                overwrites=overwrites,
                category=category,
                topic=f"Notifikasi otomatis LIVE TikTok {accounts} (read-only)",
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

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            for username in config.TIKTOK_USERNAMES:
                try:
                    await self._check_live(session, ch, username)
                except Exception as e:  # jangan sampai satu error mematikan loop
                    print(f"⚠️ TikTok monitor live @{username} error: {e}", flush=True)

    async def _report(self, username: str, kind: str, ok: bool, detail: str):
        """Kirim status cek ke #bot-logs saat pertama kali jalan & tiap kali hasilnya berubah (ok <-> gagal)."""
        key = f"{username}:{kind}"
        outcome = "ok" if ok else "fail"
        if self.outcomes.get(key) == outcome:
            return
        self.outcomes[key] = outcome
        label = kind
        if ok:
            msg = f"✅ TikTok cek {label} @{username} jalan: {detail}"
        else:
            msg = f"⚠️ TikTok cek {label} @{username} GAGAL: `{detail}`"
        print(msg, flush=True)
        logs = self.bot.get_channel(config.CHANNEL_LOGS)
        if logs:
            try:
                await logs.send(msg)
            except Exception as e:
                print(f"⚠️ Gagal kirim ke bot-logs: {e}", flush=True)

    async def _send(self, ch: discord.TextChannel, content: str, embed: discord.Embed, view: discord.ui.View):
        return await ch.send(content, embed=embed, view=view,
                             allowed_mentions=discord.AllowedMentions(everyone=config.TIKTOK_PING_EVERYONE))

    # ---------------- live

    async def _check_live(self, session: aiohttp.ClientSession, ch: discord.TextChannel, username: str):
        acc = self._acc(username)
        live, info = await fetch_live(session, username)
        await self._report(username, "live", live is not None,
                           LAST_ERROR if live is None else ("🔴 sedang LIVE" if live else "tidak live"))
        if live is None:
            # Kalau cek gagal terus (~30 menit), anggap tidak live agar live berikutnya tetap dinotif
            # (mencegah is_live nyangkut True selamanya).
            self.fail_counts[username] = self.fail_counts.get(username, 0) + 1
            if self.fail_counts[username] * config.TIKTOK_POLL_SECONDS >= 1800 and acc.get("is_live"):
                acc["is_live"] = False
                _save_state(self.state)
            return
        self.fail_counts[username] = 0
        was_live = acc.get("is_live", False)
        resend = live and was_live and acc.get("notif_version") != NOTIF_VERSION
        if live and (not was_live or resend):
            if resend:
                await self._delete_old_notif(ch, acc)
            msg = await self._send(ch, *build_live_message(username, info))
            acc["notif_version"] = NOTIF_VERSION
            acc["last_message_id"] = msg.id
            _save_state(self.state)
        if live != was_live:
            acc["is_live"] = live
            _save_state(self.state)

    async def _delete_old_notif(self, ch: discord.TextChannel, acc: dict):
        """Hapus notif live sebelumnya supaya tidak dobel saat dikirim ulang dengan tampilan baru."""
        last_id = acc.get("last_message_id")
        if last_id:
            try:
                await (await ch.fetch_message(last_id)).delete()
                return
            except Exception:
                pass
        try:
            async for m in ch.history(limit=10):
                if m.author.id == self.bot.user.id and any(
                    (e.title or "").endswith("sedang LIVE di TikTok!") for e in m.embeds
                ):
                    await m.delete()
                    break
        except Exception as e:
            print(f"⚠️ Gagal hapus notif lama: {e}", flush=True)
