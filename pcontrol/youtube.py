"""Busca no YouTube (lendo a página de resultados, sem precisar de chave de API)."""

import json
import re

import aiohttp

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def video_id_from_url(text: str) -> str | None:
    m = VIDEO_ID.search(text)
    return m.group(1) if m else None


def _text(node) -> str:
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    return "".join(run.get("text", "") for run in node.get("runs", []))


def _collect(node, out):
    if isinstance(node, dict):
        video = node.get("videoRenderer")
        if isinstance(video, dict) and video.get("videoId"):
            out.append({
                "id": video["videoId"],
                "title": _text(video.get("title")),
                "channel": _text(video.get("ownerText")),
                "duration": _text(video.get("lengthText")),
                "views": _text(video.get("shortViewCountText")) or _text(video.get("viewCountText")),
                "published": _text(video.get("publishedTimeText")),
            })
            return
        for value in node.values():
            _collect(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect(value, out)


async def search(http: aiohttp.ClientSession, query: str):
    params = {"search_query": query, "hl": "pt-BR", "gl": "BR"}
    headers = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    async with http.get(
        "https://www.youtube.com/results", params=params, headers=headers,
        cookies={"CONSENT": "YES+1"}, timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        html = await resp.text()
    start = html.find("ytInitialData")
    start = html.find("{", start) if start >= 0 else -1
    if start < 0:
        return []
    data, _ = json.JSONDecoder().raw_decode(html, start)
    results = []
    _collect(data, results)
    seen, unique = set(), []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    return unique[:30]
