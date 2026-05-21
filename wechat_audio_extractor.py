#!/usr/bin/env python3
"""
WeChat public-account article audio extractor.

Usage:
  python3 wechat_audio_extractor.py "https://mp.weixin.qq.com/s/..."

If no URL is provided, the script will prompt for one.
Downloaded audio files are saved to ~/Downloads.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_SSL_FALLBACK_WARNED = False
COOKIE_HEADER = ""


def open_url(req: urllib.request.Request, timeout: int):
    global _SSL_FALLBACK_WARNED
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            if not _SSL_FALLBACK_WARNED:
                print("提示：本机 Python 证书库校验失败，已临时跳过 HTTPS 证书校验重试。", file=sys.stderr)
                _SSL_FALLBACK_WARNED = True
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(req, timeout=timeout, context=context)
        raise


@dataclass(frozen=True)
class AudioCandidate:
    url: str
    kind: str
    title: str | None = None


@dataclass(frozen=True)
class ArticleLink:
    url: str
    title: str | None = None


def fetch_text(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://mp.weixin.qq.com/",
    }
    if COOKIE_HEADER:
        headers["Cookie"] = COOKIE_HEADER
    req = urllib.request.Request(url, headers=headers)
    with open_url(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        final_url = resp.geturl()
        return resp.read().decode(charset, errors="replace"), final_url


def fetch_bytes(url: str, referer: str) -> tuple[bytes, str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    if COOKIE_HEADER:
        headers["Cookie"] = COOKIE_HEADER
    req = urllib.request.Request(url, headers=headers)
    with open_url(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "").lower()
        final_url = resp.geturl()
        return resp.read(), content_type, final_url


def normalize_source(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\\/", "/")
    text = text.replace("\\x26", "&")
    text = text.replace("\\u0026", "&")
    text = text.replace("&amp;", "&")
    return text


def article_title(page: str) -> str:
    patterns = [
        r'var\s+msg_title\s*=\s*"([^"]+)"',
        r'var\s+album_name\s*=\s*"([^"]+)"',
        r'"album_name"\s*:\s*"([^"]+)"',
        r"<title>(.*?)</title>",
        r'property="og:title"\s+content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, re.S)
        if match:
            return clean_filename(html.unescape(match.group(1)).strip())
    return "wechat_audio"


def clean_filename(name: str, fallback: str = "wechat_audio") -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:90] or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成不重复文件名：{path}")


def numbered_stem(index: int, title: str | None, fallback: str = "wechat_audio") -> str:
    safe_title = clean_filename(title or fallback)
    return f"{index:03d} - {safe_title}"


def extension_from_content(content_type: str, url: str) -> str:
    parsed_path = urllib.parse.urlparse(url).path.lower()
    suffix = Path(parsed_path).suffix
    if suffix in {".mp3", ".m4a", ".mp4", ".aac", ".wav", ".amr", ".silk"}:
        return suffix
    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"
    if "mp4" in content_type or "m4a" in content_type:
        return ".m4a"
    if "aac" in content_type:
        return ".aac"
    if "wav" in content_type:
        return ".wav"
    if "amr" in content_type:
        return ".amr"
    return ".mp3"


def add_candidate(
    candidates: list[AudioCandidate],
    seen: set[str],
    url: str,
    kind: str,
    title: str | None = None,
) -> None:
    url = normalize_source(url).strip().strip("'\"")
    if not url:
        return
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    if not url.startswith("https://"):
        return
    if url not in seen:
        seen.add(url)
        candidates.append(AudioCandidate(url=url, kind=kind, title=title))


def add_voice_id_candidate(
    candidates: list[AudioCandidate],
    seen: set[str],
    mediaid: str,
    kind: str,
    title: str | None = None,
) -> None:
    mediaid = urllib.parse.unquote(normalize_source(mediaid)).strip()
    if not mediaid:
        return
    url = "https://res.wx.qq.com/voice/getvoice?mediaid=" + urllib.parse.quote(mediaid)
    add_candidate(candidates, seen, url, kind, title)


def extract_audio_candidates(page: str) -> list[AudioCandidate]:
    normalized = normalize_source(page)
    candidates: list[AudioCandidate] = []
    seen: set[str] = set()

    direct_url_patterns = [
        r'<audio[^>]+(?:src|data-src)=["\']([^"\']+)["\']',
        r'(?:voice_source|audio_source|play_url|song_url|audio_url|audiourl|music_url|musicurl)\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'(?:data-src|src|href)=["\'](https?://[^"\']*(?:audio|voice|music|mp3|m4a|aac|wav|amr)[^"\']*)["\']',
        r'["\'](https?://[^"\']+\.(?:mp3|m4a|aac|wav|amr)(?:\?[^"\']*)?)["\']',
        r'["\'](https?://res\.wx\.qq\.com/voice/getvoice\?[^"\']+)["\']',
        r'["\'](https?://mp\.weixin\.qq\.com/cgi-bin/readtemplate\?[^"\']+)["\']',
    ]
    for pattern in direct_url_patterns:
        for match in re.finditer(pattern, normalized, re.I | re.S):
            add_candidate(candidates, seen, match.group(1), "direct")

    quoted_id_pattern = (
        r'(?:voice_encode_fileid|voice_fileid|voiceid|voice_id|mediaid|media_id)'
        r'\s*[:=]\s*["\']([^"\']+)["\']'
    )
    for mediaid in re.findall(quoted_id_pattern, normalized, re.I):
        add_voice_id_candidate(candidates, seen, mediaid, "wechat-voice")

    query_id_pattern = (
        r'(?:voice_encode_fileid|voice_fileid|voiceid|voice_id|mediaid|media_id)'
        r'=([^&"\'\s<>]+)'
    )
    for mediaid in re.findall(query_id_pattern, normalized, re.I):
        add_voice_id_candidate(candidates, seen, mediaid, "wechat-query-voice")

    widget_pattern = r"<(?:mpvoice|mp-common-mpaudio|iframe|qqmusic|mp-audio)\b[^>]*>"
    for block in re.findall(widget_pattern, normalized, re.I):
        attrs = dict(re.findall(r'([\w:-]+)=["\']([^"\']*)["\']', block))
        mediaid = (
            attrs.get("voice_encode_fileid")
            or attrs.get("voice_fileid")
            or attrs.get("voiceid")
            or attrs.get("voice_id")
            or attrs.get("mediaid")
            or attrs.get("media_id")
        )
        name = attrs.get("name") or attrs.get("data-name") or attrs.get("title")
        if mediaid:
            add_voice_id_candidate(candidates, seen, mediaid, "wechat-widget-voice", name)
        for key, value in attrs.items():
            if looks_like_audio_url(value):
                add_candidate(candidates, seen, value, f"widget-{key}", name)

    json_like_patterns = [
        r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;",
        r"var\s+voiceList\s*=\s*(\[.*?\])\s*;",
        r"var\s+musicInfo\s*=\s*({.*?})\s*;",
        r"var\s+audioList\s*=\s*(\[.*?\])\s*;",
        r"var\s+appmsg_album_info\s*=\s*({.*?})\s*;",
    ]
    for pattern in json_like_patterns:
        for match in re.finditer(pattern, normalized, re.S):
            collect_from_jsonish(match.group(1), candidates, seen)

    return candidates


def extract_article_links(page: str, base_url: str) -> list[ArticleLink]:
    normalized = normalize_source(page)
    links: list[ArticleLink] = []
    seen: set[str] = set()

    def add_article(url: str, title: str | None = None) -> None:
        url = normalize_source(url).strip().strip("'\"")
        if not url:
            return
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/"):
            url = urllib.parse.urljoin("https://mp.weixin.qq.com", url)
        url = urllib.parse.urljoin(base_url, url)
        url = url.replace("http://mp.weixin.qq.com", "https://mp.weixin.qq.com")
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc != "mp.weixin.qq.com":
            return
        if not (parsed.path.startswith("/s") or "sn=" in parsed.query):
            return
        url = urllib.parse.urlunparse(parsed._replace(fragment=""))
        key = article_identity(url)
        if key not in seen:
            seen.add(key)
            links.append(ArticleLink(url=url, title=clean_filename(title) if title else None))

    pair_patterns = [
        r'"title"\s*:\s*"([^"]+)"[^{}]{0,1200}?"(?:content_url|url|link)"\s*:\s*"([^"]+)"',
        r'"(?:content_url|url|link)"\s*:\s*"([^"]+)"[^{}]{0,1200}?"title"\s*:\s*"([^"]+)"',
    ]
    for pattern in pair_patterns:
        for match in re.finditer(pattern, normalized, re.S):
            first, second = match.groups()
            if first.startswith(("http", "/", "\\")):
                add_article(first, second)
            else:
                add_article(second, first)

    for pattern in (
        r'href=["\']([^"\']*(?:mp\.weixin\.qq\.com/s|/s\?)[^"\']*)["\']',
        r'["\'](https?://mp\.weixin\.qq\.com/s\?[^"\']+)["\']',
        r'["\'](https?://mp\.weixin\.qq\.com/s/[^"\']+)["\']',
        r'["\'](/s\?[^"\']+)["\']',
    ):
        for match in re.finditer(pattern, normalized, re.I):
            add_article(match.group(1))

    return links


def article_identity(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    sn = query.get("sn", [""])[0]
    mid = query.get("mid", [""])[0]
    idx = query.get("idx", [""])[0]
    if sn:
        return f"sn:{sn}"
    if mid and idx:
        return f"mid:{mid}:{idx}"
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def collect_from_jsonish(blob: str, candidates: list[AudioCandidate], seen: set[str]) -> None:
    blob = normalize_source(blob)
    for url in re.findall(r'https?://[^"\'\\\s<>]+', blob):
        if looks_like_audio_url(url):
            add_candidate(candidates, seen, url, "json")

    try:
        data = json.loads(blob)
    except Exception:
        return

    def walk(value: object) -> None:
        if isinstance(value, dict):
            mediaid = None
            for key, item in value.items():
                key_lower = str(key).lower()
                if isinstance(item, str) and looks_like_audio_url(item):
                    add_candidate(candidates, seen, item, "json")
                if key_lower in {
                    "voice_encode_fileid",
                    "voice_fileid",
                    "voiceid",
                    "voice_id",
                    "mediaid",
                    "media_id",
                } and isinstance(item, str):
                    mediaid = item
                walk(item)
            if mediaid:
                add_voice_id_candidate(candidates, seen, mediaid, "json-mediaid")
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)


def looks_like_audio_url(url: str) -> bool:
    lower = url.lower()
    return any(
        marker in lower
        for marker in (
            ".mp3",
            ".m4a",
            ".aac",
            ".wav",
            ".amr",
            "getvoice?",
            "audio",
            "voice",
            "music",
            "readtemplate?t=tmpl/audio",
            "readtemplate?",
        )
    )


def audio_page_diagnosis(page: str) -> str:
    normalized = normalize_source(page).lower()
    markers = []
    for marker, label in (
        ("mpvoice", "检测到 mpvoice 组件"),
        ("mp-common-mpaudio", "检测到新版 mpaudio 组件"),
        ("voice_encode_fileid", "检测到 voice_encode_fileid 字段"),
        ("qqmusic_iframe", "检测到 QQ 音乐 iframe"),
        ("js_editor_audio", "检测到编辑器音频组件"),
        ("insertaudio", "检测到 insertaudio 插件"),
        ("getvoice?", "检测到 getvoice 链接"),
    ):
        if marker in normalized:
            markers.append(label)
    if markers:
        return "；".join(markers)
    return "页面源码里没有明显音频组件标记，可能由登录态接口或微信客户端动态加载"


def save_audio(candidate: AudioCandidate, index: int, base_title: str, referer: str, out_dir: Path) -> Path:
    stem = clean_filename(candidate.title or base_title)
    if index > 1:
        stem = f"{stem}_{index}"
    return save_audio_with_stem(candidate, stem, referer, out_dir)


def save_audio_with_stem(candidate: AudioCandidate, stem: str, referer: str, out_dir: Path) -> Path:
    data, content_type, final_url = fetch_bytes(candidate.url, referer)
    if len(data) < 512:
        raise RuntimeError("下载内容太小，可能不是有效音频")
    if "text/html" in content_type and not final_url.lower().endswith((".mp3", ".m4a", ".aac", ".wav", ".amr")):
        raise RuntimeError("下载到 HTML 页面，可能需要登录、链接过期或被微信限制")
    if not is_probably_audio(data, content_type, final_url):
        raise RuntimeError(f"下载内容不是音频，Content-Type={content_type or 'unknown'}")

    ext = extension_from_content(content_type, final_url)
    path = unique_path(out_dir / f"{clean_filename(stem)}{ext}")
    path.write_bytes(data)
    return path


def is_probably_audio(data: bytes, content_type: str, url: str) -> bool:
    lower_type = content_type.lower()
    lower_url = url.lower()
    if any(bad in lower_type for bad in ("image/", "text/html", "text/xml", "application/json")):
        return False
    if lower_type.startswith("audio/"):
        return True
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return True
    if len(data) > 12 and data[4:8] == b"ftyp":
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return True
    if data.startswith(b"#!AMR"):
        return True
    return lower_url.endswith((".mp3", ".m4a", ".aac", ".wav", ".amr"))


def download_single_article(url: str, out_dir: Path) -> list[Path]:
    page, final_article_url = fetch_text(url)
    title = article_title(page)
    candidates = extract_audio_candidates(page)
    saved: list[Path] = []
    for i, candidate in enumerate(candidates, start=1):
        try:
            saved.append(save_audio(candidate, i, title, final_article_url, out_dir))
            time.sleep(0.3)
        except Exception:
            continue
    return saved


def download_album(article_links: list[ArticleLink], album_title: str, out_root: Path) -> tuple[Path, list[Path], list[str]]:
    album_dir = unique_path(out_root / clean_filename(album_title, "wechat_album"))
    album_dir.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(len(article_links))))
    saved: list[Path] = []
    errors: list[str] = []

    for article_index, article in enumerate(article_links, start=1):
        prefix = f"{article_index:0{width}d}"
        try:
            page, final_article_url = fetch_text(article.url)
            title = article_title(page)
            if title == "wechat_audio" and article.title:
                title = article.title
            candidates = extract_audio_candidates(page)
            if not candidates:
                errors.append(f"{prefix} {title}: 未找到可下载音频；{audio_page_diagnosis(page)}")
                continue

            article_saved = 0
            for audio_index, candidate in enumerate(candidates, start=1):
                audio_suffix = "" if len(candidates) == 1 else f"-{audio_index:02d}"
                stem = f"{prefix}{audio_suffix} - {title}"
                try:
                    path = save_audio_with_stem(candidate, stem, final_article_url, album_dir)
                    saved.append(path)
                    article_saved += 1
                    print(f"已保存：{path}")
                    time.sleep(0.3)
                except Exception as exc:
                    errors.append(f"{prefix} {title}: {exc}")
            if article_saved == 0:
                errors.append(f"{prefix} {title}: 音频线索全部下载失败")
        except Exception as exc:
            errors.append(f"{prefix} {article.title or article.url}: {exc}")

    return album_dir, saved, errors


def prompt_mode() -> str:
    print("请选择解析模式：")
    print("1. 单篇/分集链接：直接提取当前文章里的音频")
    print("2. 合集链接：先提取合集里的所有分集，再逐集下载音频")
    while True:
        try:
            choice = input("请输入 1 或 2: ").strip()
        except EOFError:
            print("\n没有读取到输入。", file=sys.stderr)
            return ""
        if choice in {"1", "2"}:
            return choice
        print("输入无效，请输入 1 或 2。")


def main() -> int:
    global COOKIE_HEADER
    parser = argparse.ArgumentParser(description="提取微信公众号文章或合集中的音频并保存到下载文件夹")
    parser.add_argument("url", nargs="?", help="微信公众号文章 URL 或合集 URL")
    parser.add_argument("--mode", choices=("1", "2"), help="解析模式：1=单篇/分集，2=合集")
    parser.add_argument("--cookie", help="可选：微信网页 Cookie，遇到需要登录态的文章时使用")
    parser.add_argument("-o", "--output", default=str(Path.home() / "Downloads"), help="保存目录，默认 ~/Downloads")
    args = parser.parse_args()

    COOKIE_HEADER = args.cookie or os.environ.get("WECHAT_COOKIE", "")
    mode = args.mode or prompt_mode()
    if not mode:
        return 2
    url_label = "微信公众号分集/文章 URL" if mode == "1" else "微信公众号合集 URL"
    url = args.url or input(f"请输入{url_label}: ").strip()
    if not url:
        print("没有输入 URL。", file=sys.stderr)
        return 2

    out_dir = Path(os.path.expanduser(args.output)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("正在打开链接...")
    try:
        page, final_article_url = fetch_text(url)
    except urllib.error.HTTPError as exc:
        print(f"打开失败：HTTP {exc.code}。如果文章需要登录或已过期，请在浏览器中复制可访问的完整链接。", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"打开失败：{exc}", file=sys.stderr)
        return 1

    title = article_title(page)

    if mode == "2":
        article_links = extract_article_links(page, final_article_url)
        if not article_links:
            print("没有在合集页面中解析到分集链接。", file=sys.stderr)
            print("可能原因：合集需要微信登录态动态加载、链接不是合集页、或页面结构更新。", file=sys.stderr)
            return 1

        print(f"发现 {len(article_links)} 个分集链接，开始合集下载。")
        print(f"合集：{title}")
        album_dir, saved, errors = download_album(article_links, title, out_dir)
        if saved:
            print("\n完成。")
            print(f"已保存 {len(saved)} 个音频。")
            print(f"保存目录：{album_dir}")
            if errors:
                print(f"有 {len(errors)} 个分集未成功，可查看下面前几条原因：")
                for error in errors[:8]:
                    print(f"- {error}")
            return 0

        print("找到了分集链接，但没有成功下载到音频。", file=sys.stderr)
        for error in errors[:8]:
            print(f"- {error}", file=sys.stderr)
        print("建议：确认合集和分集都能在浏览器中直接打开；部分合集可能需要微信登录态。", file=sys.stderr)
        return 1

    candidates = extract_audio_candidates(page)
    if not candidates:
        print("没有在页面中找到音频。")
        print(f"诊断：{audio_page_diagnosis(page)}")
        print("可能原因：文章没有音频、音频由微信登录态动态加载、或你输入的是合集链接但选择了模式 1。")
        return 1

    print(f"找到 {len(candidates)} 个可能的音频链接，开始下载...")
    saved: list[Path] = []
    errors: list[str] = []
    for i, candidate in enumerate(candidates, start=1):
        try:
            path = save_audio(candidate, i, title, final_article_url, out_dir)
            saved.append(path)
            print(f"已保存：{path}")
            time.sleep(0.3)
        except Exception as exc:
            errors.append(f"{candidate.kind}: {exc}")

    if saved:
        print("\n完成。")
        print(f"保存目录：{out_dir}")
        return 0

    print("找到了音频线索，但全部下载失败。", file=sys.stderr)
    print(f"诊断：{audio_page_diagnosis(page)}", file=sys.stderr)
    for error in errors[:10]:
        print(f"- {error}", file=sys.stderr)
    print("建议：确认链接在浏览器中能打开；如果文章需要登录/关注后访问，微信可能不会允许无 Cookie 下载。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
