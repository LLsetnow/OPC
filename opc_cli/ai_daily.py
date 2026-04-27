"""AI 日报：自动收集当日 AI 技术/科研/项目新闻，LLM 整合输出专业简报

信息来源：
  - RSS: 36氪、虎嗅、IT之家、InfoQ AI
  - GitHub: AI 相关最新更新项目
  - Arxiv: AI 相关最新论文
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI

from .config import load_env, get_llm_config

# ── RSS 源配置 ────────────────────────────────────────────────────

RSS_SOURCES = {
    "36氪": "https://www.36kr.com/feed",
    "虎嗅": "https://rss.huxiu.com/",
    "IT之家": "http://www.ithome.com/rss/",
    "InfoQ AI": "https://feed.infoq.com/ai-ml-data-eng/",
}

# ── GitHub API 配置 ──────────────────────────────────────────────

GITHUB_API = "https://api.github.com/search/repositories"
GITHUB_PARAMS = {
    "q": "AI",
    "per_page": 10,
    "sort": "updated",
}

# ── Arxiv API 配置 ──────────────────────────────────────────────

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_PARAMS = {
    "search_query": "AI",
    "start": 0,
    "max_results": 5,
    "sortBy": "submittedDate",
    "sortOrder": "descending",
}

# ── 系统提示词 ──────────────────────────────────────────────────

SYSTEM_PROMPT = """# 角色
你是一位资深且权威的科技媒体编辑,擅长高效精准地整合并创作极具专业性的科技简报,特别在AI领域的技术动态、前沿学术研究成果及热门开源项目方面拥有深入的分析与整合能力。

## 工作流
### 日报输出格式
1. 日报开头显著标注"AI日报"和当天日期，例如："AI日报 | 2025年9月24日"。
2. <!!!important!!!> 根据每则AI技术新闻、每篇AI学术论文、每个AI开源项目的不同内容，在其标题开头添加一个独有的Emoji表情符号。
3. 输出的所有内容必须与AI、LLM、AIGC、大模型等技术主题高度相关，坚决排除任何无关信息、广告及营销类内容。
4. 必须为每一条目（包括AI技术新闻、AI学术论文、AI开源项目）提供其对应的原始链接。
5. 对输出的每一条新闻或项目，都进行一个简短、精准的概况描述。
6. 输出内容总量应为：**10条AI技术新闻、10条时政金融新闻、5篇AI学术论文、5个AI开源项目**。"""

SYSTEM_PROMPT_NEWS = """你是一位资深科技媒体编辑。根据提供的新闻素材，筛选出10条与AI/大模型/LLM/AIGC/机器学习/深度学习最相关的技术新闻。

要求：
1. 每条新闻标题前加一个独特的Emoji
2. 必须排除广告、营销、无关内容
3. 每条包含：标题、简短概况描述（1-2句）、原始链接
4. 不要输出二级标题（标题由外部添加）
5. 必须输出10条，素材不足时尽量从现有素材中挖掘
6. 严格按以下格式输出每条新闻：

1. 🚀 **标题内容**  
   简短概况描述。  
   [https://原始链接](https://原始链接)"""

SYSTEM_PROMPT_FINANCE = """你是一位资深财经媒体编辑。根据提供的新闻素材，筛选出10条最重要的时政金融新闻。

重点关注：宏观经济、股市行情、央行政策、地缘政治、贸易政策、科技产业政策、行业监管等。
要求：
1. 每条新闻标题前加一个独特的Emoji
2. 必须排除广告、营销、无关内容
3. 每条包含：标题、简短概况描述（1-2句）、原始链接
4. 不要输出二级标题（标题由外部添加）
5. 必须输出10条，素材不足时尽量从现有素材中挖掘
6. 严格按以下格式输出每条新闻：

1. 💼 **标题内容**  
   简短概况描述。  
   [https://原始链接](https://原始链接)"""

SYSTEM_PROMPT_PAPERS = """你是一位AI领域学术编辑。根据提供的论文素材，筛选出5篇最重要的AI学术论文。

要求：
1. 每篇论文标题前加一个独特的Emoji
2. 每篇包含：标题、简短概况描述（1-2句）、原始链接
3. 不要输出二级标题（标题由外部添加）
4. 严格按以下格式输出每篇论文：

1. 🔬 **标题内容**  
   简短概况描述。  
   [https://原始链接](https://原始链接)"""

SYSTEM_PROMPT_PROJECTS = """你是一位开源项目观察者。根据提供的项目素材，筛选出5个最值得关注的AI开源项目。

要求：
1. 每个项目标题前加一个独特的Emoji
2. 每个包含：名称+星数、简短概况描述（1-2句）、原始链接
3. 不要输出二级标题（标题由外部添加）
4. 严格按以下格式输出每个项目：

1. 🐙 **项目名 (⭐星数)**  
   简短概况描述。  
   [https://原始链接](https://原始链接)"""





# ── 获取今日日期 ──────────────────────────────────────────────────

def get_today_date() -> str:
    """调用 API 获取今日日期（北京时间），避免本地时区问题"""
    try:
        resp = requests.get("http://worldtimeapi.org/api/timezone/Asia/Shanghai", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("datetime", "")[:10]
    except Exception:
        pass
    # 回退到本地时间（北京时间 UTC+8）
    now = datetime.now(timezone(timedelta(hours=8)))
    return now.strftime("%Y-%m-%d")


# ── RSS 抓取 ──────────────────────────────────────────────────────

def fetch_rss(url: str, source_name: str) -> list[dict]:
    """抓取 RSS 源，返回文章列表"""
    articles = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        # 简单 XML 解析（避免引入额外依赖）
        text = resp.text

        # 提取 <item> 块
        items = re.findall(r"<item[^>]*>(.*?)</item>", text, re.DOTALL)

        for item in items[:20]:  # 每个源最多取 20 条
            title = _extract_tag(item, "title")
            link = _extract_tag(item, "link")
            desc = _extract_tag(item, "description")
            pub_date = _extract_tag(item, "pubDate") or _extract_tag(item, "published")

            if title:
                articles.append({
                    "source": source_name,
                    "title": _clean_html(title),
                    "link": link,
                    "description": _clean_html(desc)[:300] if desc else "",
                    "pub_date": pub_date,
                })

    except Exception as e:
        print(f"  ⚠ {source_name} RSS 抓取失败: {e}")

    return articles


def _extract_tag(xml: str, tag: str) -> str:
    """提取 XML 标签内容"""
    # 尝试 CDATA
    m = re.search(rf"<{tag}[^>]*><!\[CDATA\[(.*?)\]\]></{tag}>", xml, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 普通标签
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def _clean_html(text: str) -> str:
    """去除 HTML 标签和实体"""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return text.strip()


# ── GitHub 抓取 ──────────────────────────────────────────────────

def fetch_github() -> list[dict]:
    """抓取 GitHub AI 相关最新更新项目"""
    projects = []
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        # 如果有 GitHub token 可以提高速率限制
        gh_token = os.environ.get("GITHUB_TOKEN")
        if gh_token:
            headers["Authorization"] = f"token {gh_token}"

        resp = requests.get(GITHUB_API, params=GITHUB_PARAMS, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for repo in data.get("items", []):
            projects.append({
                "name": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "description": repo.get("description", "") or "",
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language", ""),
                "updated_at": repo.get("updated_at", ""),
            })

    except Exception as e:
        print(f"  ⚠ GitHub 抓取失败: {e}")

    return projects


# ── Arxiv 抓取 ──────────────────────────────────────────────────

def fetch_arxiv() -> list[dict]:
    """抓取 Arxiv AI 相关最新论文"""
    papers = []
    try:
        resp = requests.get(ARXIV_API, params=ARXIV_PARAMS, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # Atom feed 解析
        entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)

        for entry in entries:
            title = _extract_tag(entry, "title").replace("\n", " ").strip()
            summary = _extract_tag(entry, "summary").replace("\n", " ").strip()
            # 提取 PDF 链接
            pdf_link = ""
            m = re.search(r'href="([^"]+pdf[^"]*)"', entry)
            if m:
                pdf_link = m.group(1)
            else:
                # 回退到 entry ID
                m = re.search(r'<id>([^<]+)</id>', entry)
                if m:
                    pdf_link = m.group(1)

            authors = re.findall(r"<name>([^<]+)</name>", entry)

            published = _extract_tag(entry, "published")[:10] if _extract_tag(entry, "published") else ""

            if title:
                papers.append({
                    "title": title,
                    "url": pdf_link,
                    "summary": summary[:500],
                    "authors": ", ".join(authors[:5]),
                    "published": published,
                })

    except Exception as e:
        print(f"  ⚠ Arxiv 抓取失败: {e}")

    return papers


# ── LLM 整合 ──────────────────────────────────────────────────────

def _call_llm_with_retry(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_msg: str,
    max_retries: int = 3,
    max_tokens: int = 2048,
    label: str = "",
) -> str:
    """带重试的 LLM 调用"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            if label:
                print(f"   [{label}] 尝试 {attempt}/{max_retries}...")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = attempt * 5
                print(f"   [{label}] ⚠ 第 {attempt} 次失败: {e}")
                print(f"   等待 {wait}s 后重试...")
                time.sleep(wait)

    raise RuntimeError(f"[{label}] LLM 调用失败（重试 {max_retries} 次）: {last_error}")


def _build_news_msg(today: str, news: list[dict], task_desc: str) -> str:
    """构建新闻素材消息"""
    msg = f"今天是 {today}，{task_desc}：\n\n"
    for i, item in enumerate(news, 1):
        msg += f"{i}. [{item['source']}] {item['title']}\n"
        msg += f"   链接: {item['link']}\n"
        if item.get("description"):
            msg += f"   摘要: {item['description'][:150]}\n"
        msg += "\n"
    return msg


def generate_daily_report(
    today: str,
    news: list[dict],
    papers: list[dict],
    projects: list[dict],
    api_key: str,
    base_url: str,
    model: str,
    max_retries: int = 3,
) -> str:
    """调用 LLM 生成 AI 日报（拆分为 4 次小请求，避免超时）"""

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)

    # ── 第 1 次：AI 技术新闻 ──
    print("   🤖 生成 AI 技术新闻板块...")
    ai_msg = _build_news_msg(today, news, "请从以下新闻中筛选出10条AI相关技术新闻")
    ai_news_section = _call_llm_with_retry(client, model, SYSTEM_PROMPT_NEWS, ai_msg, max_retries, max_tokens=4096, label="AI新闻")

    # ── 第 2 次：时政金融新闻 ──
    print("   💰 生成时政金融新闻板块...")
    fin_msg = _build_news_msg(today, news, "请从以下新闻中筛选出10条最重要的时政金融新闻")
    finance_section = _call_llm_with_retry(client, model, SYSTEM_PROMPT_FINANCE, fin_msg, max_retries, max_tokens=4096, label="时政金融")

    # ── 第 3 次：论文 ──
    print("   📄 生成 AI 论文板块...")
    papers_msg = f"今天是 {today}，请从以下论文中筛选5篇最重要的AI论文：\n\n"
    for i, item in enumerate(papers, 1):
        papers_msg += f"{i}. {item['title']}\n"
        papers_msg += f"   链接: {item['url']}\n"
        if item.get("summary"):
            papers_msg += f"   摘要: {item['summary'][:200]}\n"
        papers_msg += "\n"
    papers_section = _call_llm_with_retry(client, model, SYSTEM_PROMPT_PAPERS, papers_msg, max_retries, label="论文")

    # ── 第 4 次：项目 ──
    print("   🐙 生成 AI 项目板块...")
    projects_msg = f"今天是 {today}，请从以下项目中筛选5个最值得关注的AI开源项目：\n\n"
    for i, item in enumerate(projects, 1):
        projects_msg += f"{i}. {item['name']} (⭐{item['stars']})\n"
        projects_msg += f"   链接: {item['url']}\n"
        if item.get("description"):
            projects_msg += f"   描述: {item['description'][:150]}\n"
        projects_msg += "\n"
    projects_section = _call_llm_with_retry(client, model, SYSTEM_PROMPT_PROJECTS, projects_msg, max_retries, label="项目")

    # ── 合并 ──
    report = f"# AI日报 | {today}\n\n"
    report += "## AI 技术新闻\n\n---\n\n"
    report += ai_news_section + "\n\n"
    report += "## 时政金融新闻\n\n---\n\n"
    report += finance_section + "\n\n"
    report += "## AI 学术论文\n\n---\n\n"
    report += papers_section + "\n\n"
    report += "## AI 开源项目\n\n---\n\n"
    report += projects_section + "\n"

    return report


# ── 主流程 ──────────────────────────────────────────────────────

def run_ai_daily(
    output: Optional[str] = None,
    output_dir: Optional[str] = None,
    env_file: Optional[str] = None,
    no_llm: bool = False,
    save_raw: bool = False,
):
    """运行 AI 日报收集与生成流程"""
    load_env(env_file)

    print("=" * 60)
    print("  🤖 AI 日报采集器")
    print("=" * 60)

    # 1. 获取今日日期
    print("\n📅 获取今日日期...")
    today = get_today_date()
    print(f"   今日: {today}")

    # 2. 抓取 RSS
    print("\n📰 抓取 RSS 新闻源...")
    all_news = []
    for name, url in RSS_SOURCES.items():
        print(f"   → {name}...", end=" ", flush=True)
        items = fetch_rss(url, name)
        print(f"{len(items)} 条")
        all_news.extend(items)
    print(f"   合计: {len(all_news)} 条新闻")

    # 2.5 全部新闻送入 LLM，由 LLM 分类筛选
    # 不做关键词预筛选，避免遗漏；截断到 40 条控制 token 量
    all_news = all_news[:40]
    print(f"   送入 LLM: {len(all_news)} 条新闻")

    # 3. 抓取 Arxiv
    print("\n📄 抓取 Arxiv 论文...")
    papers = fetch_arxiv()
    print(f"   获取: {len(papers)} 篇论文")

    # 4. 抓取 GitHub
    print("\n🐙 抓取 GitHub 项目...")
    projects = fetch_github()
    print(f"   获取: {len(projects)} 个项目")

    # 5. 保存原始数据（可选）
    if save_raw:
        raw_dir = Path("output")
        raw_dir.mkdir(exist_ok=True)
        raw_path = raw_dir / f"ai_daily_raw_{today}.json"
        with open(str(raw_path), "w", encoding="utf-8") as f:
            json.dump({
                "date": today,
                "news": all_news,
                "papers": papers,
                "projects": projects,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n💾 原始数据已保存: {raw_path}")

    # 6. LLM 整合（或直接输出原始素材）
    if no_llm:
        report = _format_raw_report(today, all_news, papers, projects)
    else:
        print("\n🧠 调用 LLM 生成日报...")
        api_key, base_url, model = get_llm_config()
        report = generate_daily_report(
            today=today,
            news=all_news,
            papers=papers,
            projects=projects,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    # 7. 输出
    if output:
        # --output 指定完整文件路径，优先级最高
        out_path = Path(output)
    elif output_dir:
        # --output-dir 指定目录，文件名默认 ai_daily_YYYY-MM-DD.md
        out_path = Path(output_dir) / f"ai_daily_{today}.md"
    else:
        # 默认保存到 output/ 目录
        out_path = Path("output") / f"ai_daily_{today}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out_path), "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ 日报已保存: {out_path}")

    return report


def _format_raw_report(
    today: str,
    news: list[dict],
    papers: list[dict],
    projects: list[dict],
) -> str:
    """无 LLM 时格式化原始素材"""
    lines = [f"# AI 日报 | {today}", "", "（原始素材，未经 LLM 整理）", ""]

    lines.append("## 新闻素材\n")
    for i, item in enumerate(news, 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        lines.append(f"   链接: {item['link']}")
        if item.get("description"):
            lines.append(f"   摘要: {item['description'][:200]}")
        lines.append("")

    lines.append("## 论文素材\n")
    for i, item in enumerate(papers, 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   作者: {item.get('authors', 'N/A')}")
        lines.append(f"   链接: {item['url']}")
        if item.get("summary"):
            lines.append(f"   摘要: {item['summary'][:200]}")
        lines.append("")

    lines.append("## 项目素材\n")
    for i, item in enumerate(projects, 1):
        lines.append(f"{i}. {item['name']} (⭐{item['stars']})")
        lines.append(f"   链接: {item['url']}")
        if item.get("description"):
            lines.append(f"   描述: {item['description']}")
        lines.append("")

    return "\n".join(lines)
