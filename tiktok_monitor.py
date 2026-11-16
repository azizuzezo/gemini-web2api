"""
Pemantau TikTok untuk BalikLayar AI (tanpa yt-dlp, HTTP biasa).

Untuk setiap akun di config.TIKTOK_USERNAMES:
- LIVE: cara cek sama dengan tiktok-live-connector (dipakai Patungan Yuk!):
  1) scrape SIGI_STATE di halaman /@user/live, 2) fallback ke api-live/user/room.
  liveRoom.status != 4 berarti sedang live.
- VIDEO BARU: ID video terbaru diambil dari halaman embed kreator (/embed/@user),
  judul & thumbnail dari oEmbed resmi TikTok. Kalau embed diblok, fallback ke
  "videoCount" di halaman profil (notif tanpa link video spesifik).
- Semua notif dikirim ke satu channel read-only (dibuat otomatis kalau belum ada).
- Status cek (berhasil/gagal) dilaporkan ke #bot-logs setiap kali berubah.

Konfigurasi lewat environment variable (lihat config.py):
  TIKTOK_USERNAMES, TIKTOK_POLL_SECONDS, TIKTOK_VIDEO_POLL_SECONDS, TIKTOK_PING_EVERYONE
"""

import json
import os
import re
import time

import aiohttp

try:  # Meniru TLS/HTTP2 Chrome supaya halaman profil TikTok tidak diganti halaman anti-bot
    from curl_cffi.requests import AsyncSession as _CurlSession
except Exception:  # curl_cffi belum terpasang -> cek video pakai aiohttp (kemungkinan diblok)
    _CurlSession = None

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
_VIDEO_ID_RE = re.compile(r'/video/(\d{15,21})|"(?:id|videoId|itemId)"\s*:\s*"(\d{15,21})"')
_MAX_VIDEO_AGE = 2 * 24 * 3600  # video lebih tua dari ini tidak dinotif (mis. hasil sinkron ulang)
TIKTOK_PINK = 0xFE2C55

NOTIF_VERSION = 3  # naikkan kalau tampilan notif live diubah -> live yang sedang jalan dikirim ulang sekali

LAST_ERROR = ""  # alasan gagal terakhir (dipakai laporan #bot-logs)


def profile_url(username: str) -> str:
    return f"https://www.tiktok.com/@{username}"


def live_url(username: str) -> str:
    return f"{profile_url(username)}/live"


def video_url(username: str, video_id: str | int) -> str:
    return f"{profile_url(username)}/video/{video_id}"


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


# ------------------------------------------------------------------ video baru

def _video_time(video_id: int) -> int:
    """ID video TikTok berbasis waktu: 32 bit teratas = unix timestamp upload."""
    return int(video_id) >> 32


def _snip(html: str, n: int = 160) -> str:
    """Potongan awal halaman (untuk diagnosa di #bot-logs)."""
    return re.sub(r"\s+", " ", html[:n]).replace("`", "'")


class VideoHttp:
    """GET untuk cek video baru: curl_cffi (meniru Chrome) kalau terpasang, kalau tidak aiohttp."""

    def __init__(self, aio_session: aiohttp.ClientSession | None):
        self.aio = aio_session
        self.curl = None

    @property
    def engine(self) -> str:
        return "curl_cffi" if self.curl else "aiohttp"

    async def __aenter__(self):
        if _CurlSession is not None:
            self.curl = _CurlSession(impersonate="chrome", timeout=20)
        return self

    async def __aexit__(self, *exc):
        if self.curl is not None:
            try:
                await self.curl.close()
            except Exception:
                pass

    async def get(self, url: str, params: dict | None = None) -> tuple[int, str]:
        if self.curl is not None:
            # User-Agent sengaja tidak di-set: biar cocok dengan sidik jari Chrome yang ditiru
            r = await self.curl.get(url, params=params, headers={
                "Accept-Language": _HEADERS["Accept-Language"], "Referer": _HEADERS["Referer"]})
            return r.status_code, r.text
        async with self.aio.get(url, params=params) as r:
            return r.status, await r.text()


def _valid_ids(raw) -> list[int]:
    """Saring angka yang memang ID video (timestamp di dalamnya masuk akal), terbaru dulu."""
    now = time.time()
    ids = {int(i) for i in raw if str(i).isdigit()}
    return sorted((i for i in ids if 1451606400 <= _video_time(i) <= now + 86400), reverse=True)


async def fetch_latest_video_ids(http: VideoHttp, username: str, sec_uid: str | None = None) -> list[int]:
    """ID video terbaru dulu, dari halaman embed kreator lalu API item_list. Raise kalau semua gagal."""
    tried = []
    for url in (f"https://www.tiktok.com/embed/@{username}",
                f"https://www.tiktok.com/embed/@{username}?lang=en-US&embedFrom=oembed"):
        status, html = await http.get(url)
        ids = _valid_ids(a or b for a, b in _VIDEO_ID_RE.findall(html))
        if ids:
            return ids
        tried.append(f"embed HTTP {status} {len(html)}b")
    if sec_uid:
        params = {"aid": "1988", "count": "10", "cursor": "0", "secUid": sec_uid}
        status, body = await http.get("https://www.tiktok.com/api/post/item_list/", params)
        try:
            items = (json.loads(body) or {}).get("itemList") or []
        except Exception:
            items = []
        ids = _valid_ids(it.get("id") for it in items)
        if ids:
            return ids
        tried.append(f"item_list HTTP {status} {len(body)}b")
    else:
        tried.append("item_list dilewati (secUid tidak ada)")
    raise ValueError(" ; ".join(tried))


async def fetch_profile(http: VideoHttp, username: str) -> dict:
    """{'videoCount', 'nickname', 'avatar', 'secUid'} dari halaman profil. Raise kalau gagal."""
    status, html = await http.get(profile_url(username))
    m = re.search(r'"videoCount"\s*:\s*"?(\d+)', html)
    if not m:
        # Ambil statusCode TikTok dari data halaman supaya alasan gagalnya jelas
        # (10202 = akun tidak ada, 10221/10222 = akun diblokir/privat, dll.)
        code = re.search(r'"webapp\.user-detail"\s*:\s*\{[^{}]*?"statusCode"\s*:\s*(-?\d+)', html)
        hint = f", statusCode TikTok {code.group(1)}" if code else ""
        raise ValueError(f"videoCount tidak ada (HTTP {status}{hint}, {len(html)} byte: '{_snip(html, 100)}')")

    def _find(key: str) -> str | None:
        f = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.){{1,300}})"', html)
        if not f:
            return None
        try:
            return json.loads(f'"{f.group(1)}"')
        except Exception:
            return f.group(1)

    return {
        "videoCount": int(m.group(1)),
        "nickname": _find("nickname"),
        "avatar": _find("avatarLarger"),
        "secUid": _find("secUid"),
    }


async def fetch_oembed(http: VideoHttp, url: str) -> dict:
    try:
        status, body = await http.get("https://www.tiktok.com/oembed", {"url": url})
        return json.loads(body) if status == 200 else {}
    except Exception:
        return {}


def build_video_message(username: str, video_id: int | None, oembed: dict,
                        profile: dict | None) -> tuple[str, discord.Embed, discord.ui.View]:
    profile = profile or {}
    nickname = profile.get("nickname") or oembed.get("author_name") or username
    avatar = profile.get("avatar")
    url = video_url(username, video_id) if video_id else profile_url(username)
    caption = (oembed.get("title") or "").strip()
    if len(caption) > 300:
        caption = caption[:297] + "..."

    content = (
        f"🎬 **{nickname} baru upload video baru!**\n"
        f"Langsung tonton, kasih like & komen biar makin FYP 🔥"
    )
    embed = discord.Embed(
        title="📲 Video baru di TikTok",
        url=url,
        description=(
            (f"> {caption}\n\n" if caption else "")
            + f"**[👉 Tonton videonya di sini]({url})**"
        ),
        color=TIKTOK_PINK,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_author(name=f"{nickname} (@{username})", url=profile_url(username), icon_url=avatar or None)
    if avatar:
        embed.set_thumbnail(url=avatar)
    if oembed.get("thumbnail_url"):
        embed.set_image(url=oembed["thumbnail_url"])
    if video_id:
        embed.add_field(name="🕒 Diupload", value=f"<t:{_video_time(video_id)}:R>", inline=True)
    embed.set_footer(text="BalikLayar AI • notifikasi video baru otomatis")

    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Tonton video", emoji="▶️", url=url))
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
        self.last_video_check = 0.0
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
                topic=f"Notifikasi otomatis LIVE & video baru TikTok {accounts} (read-only)",
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

        do_videos = time.monotonic() - self.last_video_check >= config.TIKTOK_VIDEO_POLL_SECONDS
        if do_videos:
            self.last_video_check = time.monotonic()

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            async with VideoHttp(session) as http:
                for username in config.TIKTOK_USERNAMES:
                    checks = [(self._check_live, session)] + ([(self._check_video, http)] if do_videos else [])
                    for check, client in checks:
                        try:
                            await check(client, ch, username)
                        except Exception as e:  # jangan sampai satu error mematikan loop
                            print(f"⚠️ TikTok monitor {check.__name__} @{username} error: {e}", flush=True)

    async def _report(self, username: str, kind: str, ok: bool, detail: str):
        """Kirim status cek ke #bot-logs saat pertama kali jalan & tiap kali hasilnya berubah (ok <-> gagal)."""
        key = f"{username}:{kind}"
        outcome = "ok" if ok else "fail"
        if self.outcomes.get(key) == outcome:
            return
        self.outcomes[key] = outcome
        label = "live" if kind == "live" else "video baru"
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

    # ---------------- video baru

    async def _check_video(self, http: VideoHttp, ch: discord.TextChannel, username: str):
        acc = self._acc(username)
        engine = getattr(http, "engine", "?")
        errors = []

        profile = None
        try:
            profile = await fetch_profile(http, username)
        except Exception as e:
            errors.append(f"profil: {e}")

        ids = None
        try:
            ids = await fetch_latest_video_ids(http, username, (profile or {}).get("secUid"))
        except Exception as e:
            errors.append(f"daftar video: {e}")

        if ids:
            await self._report(username, "video", True, f"video terbaru {ids[0]} ({engine})")
            last = acc.get("last_video_id")
            if last is None:
                # Pertama kali (atau habis fallback): catat saja, jangan spam video lama
                acc["last_video_id"] = ids[0]
            else:
                new_ids = sorted(i for i in ids if i > last)[-3:]  # maksimal 3 sekaligus, terlama dulu
                for vid in new_ids:
                    if time.time() - _video_time(vid) > _MAX_VIDEO_AGE:
                        continue
                    oembed = await fetch_oembed(http, video_url(username, vid))
                    await self._send(ch, *build_video_message(username, vid, oembed, profile))
                acc["last_video_id"] = max(last, ids[0])
            if profile:
                acc["video_count"] = profile["videoCount"]
            _save_state(self.state)
            return

        if profile:
            # Daftar video tidak didapat -> pakai jumlah video di profil (tanpa link video spesifik)
            await self._report(username, "video", True,
                               f"pakai jumlah video ({profile['videoCount']}, {engine}); {errors[-1][:150]}")
            count = profile["videoCount"]
            prev = acc.get("video_count")
            if prev is not None and count > prev:
                await self._send(ch, *build_video_message(username, None, {}, profile))
                # Reset ID supaya saat daftar video jalan lagi, video yang sama tidak dinotif dua kali
                acc.pop("last_video_id", None)
            acc["video_count"] = count
            _save_state(self.state)
            return

        await self._report(username, "video", False, f"[{engine}] " + " | ".join(errors)[:280])
