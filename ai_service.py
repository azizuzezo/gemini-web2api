import aiohttp
import json
import config

SYSTEM_PROMPT = """Kamu adalah BalikLayar AI Assistant, asisten resmi komunitas kreator video AI dan affiliate duacincin.id / BalikLayar AI.

Keahlian utamamu:
1. Brainstorming ide konten video pendek (TikTok, Reels, YouTube Shorts) yang unik dan berpotensi FYP.
2. Merancang Hook 3 detik pertama yang memancing rasa penasaran audiens (pattern interrupt).
3. Strategi affiliate marketing: storytelling, soft-selling, review jujur, dan Call-To-Action (CTA) berkonversi tinggi.
4. Tips penggunaan tools video AI (CapCut, prompt AI gambar/video, voiceover AI).

Gaya berkomunikasi:
- Ramah, suportif, berenergi positif, dan profesional seperti mentor kreator.
- Gunakan Bahasa Indonesia yang luwes (bisa gunakan istilah kreator: hook, CTR, retention, CTA, affiliate, prompt).
- Jawaban terstruktur, praktis, langsung ke solusi, dan enak dibaca di Discord (gunakan bullet point atau bold).
- Jangan melebihi 1800 karakter agar muat dalam satu pesan Discord.
"""

async def query_ai(prompt: str, user_name: str = "Kreator") -> str:
    # 1. Coba DuaCincin (Local Gemini-Web2API Proxy) terlebih dahulu
    duacincin_url = getattr(config, "DUACINCIN_API_URL", "http://127.0.0.1:8081/v1/chat/completions")
    duacincin_key = getattr(config, "DUACINCIN_API_KEY", "sk-csportal")
    
    headers = {
        "Authorization": f"Bearer {duacincin_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": getattr(config, "AI_MODEL", "gemini-2.5-flash"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Pertanyaan dari {user_name}:\n{prompt}"}
        ],
        "max_tokens": 800,
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(duacincin_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "Maaf, respon kosong.")
    except Exception as e:
        # Jika DuaCincin lokal belum berjalan atau timeout, lanjut ke fallback API key
        pass

    # 2. Fallback ke Google AI Studio Gemini API jika GEMINI_API_KEY diset
    gemini_key = getattr(config, "GEMINI_API_KEY", "").strip()
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload_gemini = {
            "contents": [{"parts": [{"text": f"Pertanyaan dari {user_name}:\n{prompt}"}]}],
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {"maxOutputTokens": 800, "temperature": 0.7}
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload_gemini, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "Maaf, tidak ada respon.")
        except Exception:
            pass

    # 3. Fallback ke OpenAI API jika OPENAI_API_KEY diset
    openai_key = getattr(config, "OPENAI_API_KEY", "").strip()
    if openai_key:
        url_openai = "https://api.openai.com/v1/chat/completions"
        headers_openai = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url_openai, headers=headers_openai, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "Maaf, tidak ada respon.")
        except Exception:
            pass

    return (
        "🤖 **AI Belum Terhubung ke Host DuaCincin**\n\n"
        "Pastikan service `gemini-web2api` sudah berjalan di port 8081, atau masukkan API key cadangan di `config.py`."
    )
