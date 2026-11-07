"""Export public X Articles to Markdown with locally saved images.

Article content is retrieved from FxTwitter's public API because yt-dlp's X
extractor only exposes ordinary post metadata. X account cookies are never sent
to FxTwitter; protected or age-restricted content is not available here.
"""

from __future__ import annotations

import json
import mimetypes
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


class XArticleDownloadError(RuntimeError):
    """An X Article could not be fetched, rendered, or saved."""


_API_HOST = "api.fxtwitter.com"
_MEDIA_HOSTS = {"pbs.twimg.com", "video.twimg.com", "abs.twimg.com"}
_URL_RE = re.compile(r"^https?://(?:www\.)?(?:x|twitter)\.com/", re.IGNORECASE)
_ARTICLE_PATH_RE = re.compile(r"^/([^/]+)/(article|status)/(\d+)/?$")
_MAX_IMAGE_BYTES = 50 * 1024 * 1024
_REQUEST_TIMEOUT = (10, 45)


def _source_endpoint(url: str) -> tuple[str, str]:
    """Return the author/status path accepted by FxTwitter for an X URL."""
    parsed = urlparse(url)
    if not _URL_RE.match(url) or parsed.hostname not in {
        "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    }:
        raise XArticleDownloadError("--article 需要 x.com 或 twitter.com 的文章/帖子链接。")

    match = _ARTICLE_PATH_RE.fullmatch(parsed.path)
    if match:
        handle, route_kind, status_id = match.groups()
        if handle.lower() == "i" and route_kind == "article":
            raise XArticleDownloadError(
                "无法从 x.com/i/article 链接确定作者。请使用作者的 "
                "x.com/<用户名>/article/<编号> 或对应帖子链接。"
            )
        return handle, status_id

    if re.fullmatch(r"/i/(?:web/)?status/\d+/?", parsed.path):
        return "i", parsed.path.rstrip("/").split("/")[-1]

    if re.fullmatch(r"/i/article/\d+/?", parsed.path):
        raise XArticleDownloadError(
            "无法从 x.com/i/article 链接确定作者。请使用作者的 "
            "x.com/<用户名>/article/<编号> 或对应帖子链接。"
        )
    raise XArticleDownloadError(
        "无法识别 X 文章链接；请提供 x.com/<用户名>/article/<编号> "
        "或分享该文章的帖子链接。"
    )


def _fetch_tweet(session: requests.Session, status_id: str) -> dict:
    """Fetch one public post and its optional long-form article payload."""
    api_url = f"https://{_API_HOST}/2/status/{status_id}"
    try:
        response = session.get(api_url, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        raise XArticleDownloadError(
            f"获取 X 文章失败（FxTwitter API 网络请求失败）：{error}"
        ) from error

    if urlparse(response.url).hostname != _API_HOST:
        raise XArticleDownloadError("FxTwitter API 将请求重定向到非预期域名，已停止下载。")
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError) as error:
        raise XArticleDownloadError("FxTwitter API 返回了无法解析的 JSON。") from error

    if not isinstance(payload, dict):
        raise XArticleDownloadError("FxTwitter API 返回了无法识别的数据结构。")
    status = payload.get("status") or payload.get("tweet")
    if payload.get("code") != 200 or not isinstance(status, dict):
        detail = payload.get("message") or payload.get("error") or "内容不存在或当前不可访问"
        raise XArticleDownloadError(f"FxTwitter API 无法读取该帖子：{detail}")
    return status


def _entity_map(raw_entity_map) -> dict[str, dict]:
    if isinstance(raw_entity_map, dict):
        return {str(key): value for key, value in raw_entity_map.items() if isinstance(value, dict)}
    result = {}
    if isinstance(raw_entity_map, list):
        for item in raw_entity_map:
            if isinstance(item, dict) and isinstance(item.get("value"), dict):
                result[str(item.get("key", ""))] = item["value"]
    return result


def _media_urls(article: dict) -> tuple[dict[str, str], list[str], str | None]:
    """Collect article media IDs, original URLs, and an optional cover URL."""
    media_by_id: dict[str, str] = {}
    image_urls: list[str] = []
    raw_media = article.get("media_entities") or []
    if isinstance(raw_media, dict):
        raw_media = list(raw_media.values())
    for media in raw_media:
        if not isinstance(media, dict):
            continue
        info = media.get("media_info") if isinstance(media.get("media_info"), dict) else {}
        media_id = media.get("media_id") or media.get("id") or media.get("media_key")
        image_url = info.get("original_img_url") or media.get("media_url_https") or media.get("url")
        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            continue
        image_url = _prefer_original_size(image_url)
        if media_id is not None:
            media_by_id[str(media_id)] = image_url
        image_urls.append(image_url)

    content = article.get("content")
    if isinstance(content, dict):
        for entity in _entity_map(content.get("entityMap")).values():
            if str(entity.get("type", "")).upper() != "MARKDOWN":
                continue
            data = entity.get("data", {})
            markdown_source = data.get("markdown") if isinstance(data, dict) else None
            if not isinstance(markdown_source, str):
                continue
            for match in re.finditer(r"!\[[^\]]*\]\((https://[^\s)]+)\)", markdown_source):
                image_url = _prefer_original_size(match.group(1))
                if _allowed_media_url(image_url):
                    image_urls.append(image_url)

    cover_media = article.get("cover_media")
    cover_info = cover_media.get("media_info", {}) if isinstance(cover_media, dict) else {}
    cover_url = cover_info.get("original_img_url") if isinstance(cover_info, dict) else None
    if isinstance(cover_url, str) and cover_url.startswith("https://"):
        cover_url = _prefer_original_size(cover_url)
        image_urls.insert(0, cover_url)
    else:
        cover_url = None
    return media_by_id, list(dict.fromkeys(image_urls)), cover_url


def _prefer_original_size(url: str) -> str:
    """Ask X's image CDN for the original image where the URL has a size key."""
    if "pbs.twimg.com/" not in url or "name=" not in url:
        return url
    return re.sub(r"([?&]name=)[^&]+", r"\g<1>orig", url, count=1)


def _allowed_media_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in _MEDIA_HOSTS


def _download_image(session: requests.Session, url: str, prefix: Path) -> Path:
    """Download one X-hosted image with redirect, content type, and size checks."""
    if not _allowed_media_url(url):
        raise XArticleDownloadError(f"文章图片不是受支持的 X 媒体链接：{url}")
    try:
        response = session.get(url, stream=True, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as error:
        raise XArticleDownloadError(f"下载文章图片失败：{error}") from error

    temporary_path: Path | None = None
    try:
        response.raise_for_status()
        if not _allowed_media_url(response.url):
            raise XArticleDownloadError("X 图片下载重定向到非预期域名，已停止下载。")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise XArticleDownloadError(f"X 图片返回了非图片内容（{content_type or '未知类型'}）。")
        try:
            content_length = int(response.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > _MAX_IMAGE_BYTES:
            raise XArticleDownloadError("文章图片超过 50 MB 限制。")

        extension = mimetypes.guess_extension(content_type) or Path(urlparse(url).path).suffix
        if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
            extension = ".img"
        destination = prefix.with_suffix(extension)
        temporary_path = destination.with_name(destination.name + ".part")
        total = 0
        with temporary_path.open("wb") as image_file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _MAX_IMAGE_BYTES:
                    raise XArticleDownloadError("文章图片超过 50 MB 限制。")
                image_file.write(chunk)
        if total == 0:
            raise XArticleDownloadError("X 图片响应为空。")
        temporary_path.replace(destination)
        temporary_path = None
        return destination
    except requests.RequestException as error:
        raise XArticleDownloadError(f"下载文章图片失败：{error}") from error
    finally:
        response.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_markdown_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _markdown_link_url(url: str) -> str:
    return url.strip().replace(" ", "%20").replace(")", "%29")


def _render_inline(text: str, block: dict, entities: dict[str, dict]) -> str:
    """Render Draft.js-style inline style and link ranges as Markdown."""
    ranges: list[tuple[int, int, str, str | None]] = []
    for item in block.get("inlineStyleRanges", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            start, end = int(item.get("offset", 0)), int(item.get("offset", 0)) + int(item.get("length", 0))
        except (TypeError, ValueError):
            continue
        if end > start:
            ranges.append((max(0, start), min(len(text), end), str(item.get("style", "")).upper(), None))
    for item in block.get("entityRanges", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            start, end = int(item.get("offset", 0)), int(item.get("offset", 0)) + int(item.get("length", 0))
        except (TypeError, ValueError):
            continue
        entity = entities.get(str(item.get("key", "")), {})
        data = entity.get("data", {}) if isinstance(entity, dict) else {}
        if str(entity.get("type", "")).upper() not in {"LINK", "URL"} or not isinstance(data, dict):
            continue
        target = data.get("url") or data.get("href")
        if isinstance(target, str) and urlparse(target).scheme in {"http", "https"} and end > start:
            ranges.append((max(0, start), min(len(text), end), "LINK", target))

    boundaries = {0, len(text)}
    for start, end, _, _ in ranges:
        boundaries.add(max(0, min(len(text), start)))
        boundaries.add(max(0, min(len(text), end)))
    points = sorted(boundaries)
    rendered: list[str] = []
    for start, end in zip(points, points[1:]):
        segment = text[start:end]
        if not segment:
            continue
        active = [(style, target) for left, right, style, target in ranges if left <= start and right >= end]
        link = next((target for style, target in active if style == "LINK"), None)
        value = _safe_markdown_text(segment)
        if link:
            value = f"[{value}]({_markdown_link_url(link)})"
        styles = {style for style, _ in active}
        if "CODE" in styles or "CODEBLOCK" in styles:
            value = value.replace("`", "\\`")
            value = f"`{value}`"
        else:
            if "BOLD" in styles:
                value = f"**{value}**"
            if "ITALIC" in styles:
                value = f"*{value}*"
        rendered.append(value)
    return "".join(rendered)


def _render_article_body(
    article: dict,
    media_by_id: dict[str, str],
    local_images: dict[str, str],
) -> tuple[str, set[str]]:
    content = article.get("content")
    if not isinstance(content, dict):
        raise XArticleDownloadError("FxTwitter 没有返回可渲染的文章正文。")
    entities = _entity_map(content.get("entityMap"))

    # Newer FxTwitter responses include the provider-rendered Markdown as a
    # MARKDOWN entity. Prefer it because it preserves richer inline formatting.
    for entity in entities.values():
        if str(entity.get("type", "")).upper() != "MARKDOWN":
            continue
        data = entity.get("data", {})
        markdown_source = data.get("markdown") if isinstance(data, dict) else None
        if not isinstance(markdown_source, str) or not markdown_source.strip():
            continue
        referenced_images: set[str] = set()

        def localize_image(match: re.Match) -> str:
            prefix, image_url, suffix = match.groups()
            referenced_images.add(image_url)
            image_path = local_images.get(image_url)
            if image_path is None:
                image_path = next(
                    (
                        path for remote_url, path in local_images.items()
                        if urlparse(remote_url).path == urlparse(image_url).path
                    ),
                    None,
                )
            return f"{prefix}{_markdown_link_url(image_path or image_url)}{suffix}"

        markdown_source = re.sub(
            r"(!\[[^\]]*\]\()([^\s)]+)(\))",
            localize_image,
            markdown_source,
        )
        return markdown_source.strip(), referenced_images

    if not isinstance(content.get("blocks"), list):
        raise XArticleDownloadError("FxTwitter 没有返回可渲染的文章正文。")
    rendered_blocks: list[str] = []
    referenced_images: set[str] = set()

    for block in content["blocks"]:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "unstyled")).lower()
        text = str(block.get("text", ""))
        if block_type == "atomic":
            images: list[str] = []
            for item in block.get("entityRanges", []) or []:
                if not isinstance(item, dict):
                    continue
                entity = entities.get(str(item.get("key", "")), {})
                if not isinstance(entity, dict) or str(entity.get("type", "")).upper() != "MEDIA":
                    continue
                data = entity.get("data", {})
                media_items = data.get("mediaItems", []) if isinstance(data, dict) else []
                for media_item in media_items if isinstance(media_items, list) else []:
                    if not isinstance(media_item, dict):
                        continue
                    media_id = media_item.get("mediaId") or media_item.get("media_id")
                    image_url = media_by_id.get(str(media_id))
                    if image_url:
                        images.append(image_url)
            for image_url in images:
                referenced_images.add(image_url)
                local_path = local_images.get(image_url, image_url)
                rendered_blocks.append(f"![文章图片]({_markdown_link_url(local_path)})")
            continue

        inline = _render_inline(text, block, entities).strip()
        if not inline and block_type not in {"divider", "horizontal-rule", "hr"}:
            continue
        if block_type in {"header-one", "heading-one"}:
            output = f"# {inline}"
        elif block_type in {"header-two", "heading-two"}:
            output = f"## {inline}"
        elif block_type in {"header-three", "heading-three"}:
            output = f"### {inline}"
        elif block_type in {"unordered-list-item", "list-item-unordered"}:
            try:
                depth = max(0, min(int(block.get("depth", 0) or 0), 8))
            except (TypeError, ValueError):
                depth = 0
            output = f"{'  ' * depth}- {inline}"
        elif block_type in {"ordered-list-item", "list-item-ordered"}:
            try:
                depth = max(0, min(int(block.get("depth", 0) or 0), 8))
            except (TypeError, ValueError):
                depth = 0
            output = f"{'  ' * depth}1. {inline}"
        elif block_type in {"blockquote", "pullquote"}:
            output = "\n".join(f"> {line}" for line in inline.splitlines())
        elif block_type in {"code-block", "code"}:
            fence = "````" if "```" in text else "```"
            output = f"{fence}\n{text}\n{fence}"
        elif block_type in {"divider", "horizontal-rule", "hr"}:
            output = "---"
        else:
            output = inline
        rendered_blocks.append(output)

    return "\n\n".join(rendered_blocks).strip(), referenced_images


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    slug = re.sub(r"[^\w\s-]", "", normalized, flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "-", slug.strip()).strip("-_")
    return slug[:72].rstrip("-_") or "x-article"


def _frontmatter(metadata: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def download_article(url: str, output_dir: str) -> str:
    """Save a public X Article as Markdown and download its X-hosted images.

    Returns the absolute path to the Markdown file. Images are stored beside it
    in a dedicated ``*_images`` directory and linked by relative paths.
    """
    handle, status_id = _source_endpoint(url)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "OPC-CLI/1.0 (+https://github.com/LLsetnow/OPC)",
    })
    try:
        tweet = _fetch_tweet(session, status_id)
        article = tweet.get("article")
        if not isinstance(article, dict):
            raise XArticleDownloadError(
                "该链接没有可访问的 X 长文 Article。请确认是长文链接或分享该文章的帖子链接；"
                "受保护、年龄限制或已删除的内容无法通过此公共接口读取。"
            )

        title = str(article.get("title") or "").strip()
        if not title:
            raw_text = tweet.get("raw_text")
            fallback_text = tweet.get("text") or (raw_text.get("text") if isinstance(raw_text, dict) else None)
            title = str(fallback_text or "X Article").splitlines()[0][:100]
        author_data = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
        author_name = str(author_data.get("name") or handle).strip()
        author_handle = str(author_data.get("screen_name") or handle).strip().lstrip("@")
        published = str(article.get("created_at") or tweet.get("created_at") or "")

        media_by_id, image_urls, cover_url = _media_urls(article)
        image_dir_name = f"{_slugify(title)}-{status_id}_images"
        image_dir = destination / image_dir_name
        local_images: dict[str, str] = {}
        image_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        for index, image_url in enumerate(image_urls, start=1):
            prefix = image_dir / f"image-{index:03d}"
            try:
                saved = _download_image(session, image_url, prefix)
            except (XArticleDownloadError, OSError) as error:
                warnings.append(f"{image_url}: {error}")
                continue
            local_images[image_url] = f"{image_dir_name}/{saved.name}"

        body, referenced_images = _render_article_body(article, media_by_id, local_images)
        if cover_url and cover_url in local_images and cover_url not in referenced_images:
            body = f"![封面]({_markdown_link_url(local_images[cover_url])})\n\n{body}".strip()
        if not body:
            raise XArticleDownloadError("文章正文为空，没有生成 Markdown 文件。")

        canonical_url = str(article.get("url") or url)
        saved_at = datetime.now(timezone.utc).astimezone().date().isoformat()
        metadata = {
            "title": title,
            "author": f"{author_name} (@{author_handle})",
            "source": url,
            "canonical_url": canonical_url,
            "published": published,
            "saved_at": saved_at,
        }
        markdown = f"{_frontmatter(metadata)}\n\n# {title}\n\n{body}\n"
        output_path = destination / f"{_slugify(title)}-{status_id}.md"
        output_path.write_text(markdown, encoding="utf-8")
        print(f"文章已保存为 Markdown: {output_path}")
        print(f"图片目录: {image_dir}")
        if warnings:
            print(f"提示: {len(warnings)} 张图片下载失败，Markdown 保留了原始图片链接。")
            for warning in warnings:
                print(f"  - {warning}")
        return str(output_path)
    finally:
        session.close()
