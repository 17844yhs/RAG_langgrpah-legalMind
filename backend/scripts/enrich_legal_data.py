"""法律数据扩充：LawRefBook/Laws（GitHub 开源仓库）→ 法条按条入库 + 典型案例全文入库

数据源：https://github.com/LawRefBook/Laws （开源法律文本，jsdelivr CDN 下载）
- 法条：核心法律全文按"第X条"粒度切分入库（现有 law_001~020，新增从 law_100 起）
- 案例：官方案例目录全部典型案例（案情+裁判结果+分析），content 填充真实正文

幂等：法条按 id 前缀 law_1 判断，案例按 title 判断，可重复执行。
频率控制：每个请求间隔 0.6s，3 次重试退避。
"""
import asyncio
import os
import re
import sys
import time
import urllib.request
import ssl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

REPO_RAW = "https://cdn.jsdelivr.net/gh/LawRefBook/Laws@master/"
REPO_RAW_FALLBACK = "https://raw.githubusercontent.com/LawRefBook/Laws/master/"
API_BASE = "https://api.github.com/repos/LawRefBook/Laws/contents/"


def fetch(url: str, retries: int = 3) -> str | None:
    """带重试退避的 GET，返回 utf-8 文本"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if i == retries - 1:
                print(f"  [FAIL] {url[:80]}: {type(e).__name__}: {e}")
                return None
            time.sleep(0.8 * (i + 1))
    return None


def fetch_repo_file(path: str) -> str | None:
    """下载仓库文件：jsdelivr 优先，raw 兜底"""
    encoded = urllib.request.quote(path)
    body = fetch(REPO_RAW + encoded)
    if body is None:
        body = fetch(REPO_RAW_FALLBACK + encoded)
    return body


def list_repo_dir(path: str) -> list[str]:
    """列仓库目录文件名"""
    body = fetch(API_BASE + urllib.request.quote(path))
    if body is None:
        return []
    import json
    items = json.loads(body)
    return [i["name"] for i in items if i["type"] == "file"]


# ── 法条清单：(目录, 文件名模式, 显示名, category) ──
LAW_SOURCES = [
    ("民法典", "总则.md", "中华人民共和国民法典总则编", "民法总则"),
    ("民法典", "物权编.md", "中华人民共和国民法典物权编", "物权"),
    ("民法典", "合同编.md", "中华人民共和国民法典合同编", "合同"),
    ("民法典", "人格权编.md", "中华人民共和国民法典人格权编", "人格权"),
    ("民法典", "婚姻家庭编.md", "中华人民共和国民法典婚姻家庭编", "婚姻家庭"),
    ("民法典", "继承编.md", "中华人民共和国民法典继承编", "继承"),
    ("民法典", "侵权责任编.md", "中华人民共和国民法典侵权责任编", "侵权"),
    ("社会法", "劳动合同法", "中华人民共和国劳动合同法", "劳动"),
    ("社会法", "劳动法", "中华人民共和国劳动法", "劳动"),
    ("社会法", "社会保险法", "中华人民共和国社会保险法", "劳动"),
    ("社会法", "反家庭暴力法", "中华人民共和国反家庭暴力法", "婚姻家庭"),
    ("民法商法", "公司法(2023", "中华人民共和国公司法", "公司"),
    ("民法商法", "保险法(2015", "中华人民共和国保险法", "保险"),
    ("经济法", "消费者权益保护法", "中华人民共和国消费者权益保护法", "消费"),
    ("经济法", "产品质量法", "中华人民共和国产品质量法", "消费"),
    ("行政法", "道路交通安全法", "中华人民共和国道路交通安全法", "交通"),
    ("行政法", "个人信息保护法", "中华人民共和国个人信息保护法", "个人信息"),
    ("刑法", "刑法.md", "中华人民共和国刑法", "刑事"),
    ("诉讼与非诉讼程序法", "民事诉讼法(2023", "中华人民共和国民事诉讼法", "程序"),
    ("诉讼与非诉讼程序法", "劳动争议调解仲裁法", "中华人民共和国劳动争议调解仲裁法", "劳动"),
    ("诉讼与非诉讼程序法", "行政诉讼法", "中华人民共和国行政诉讼法", "行政"),
]

ARTICLE_RE = re.compile(r"(?=第[一二三四五六七八九十百千零〇]+条)")
LAW_CITE_RE = re.compile(r"《([^》]{2,40})》第[一二三四五六七八九十百千零〇]+条[^。；\n]{0,30}")


def resolve_filename(dir_name: str, pattern: str) -> str | None:
    """目录下按前缀匹配文件名（多版本取最后一个=最新版）"""
    names = list_repo_dir(dir_name)
    matches = [n for n in names if n.startswith(pattern) and n.endswith(".md")]
    if not matches:
        print(f"  [WARN] {dir_name}/{pattern} 无匹配文件，可选: {names[:10]}")
        return None
    return matches[-1]


def split_articles(md_text: str) -> list[tuple[str, str]]:
    """按"第X条"切分条文，返回 [(条号标题, 条文正文)]"""
    # 去掉 INFO END 前的元信息和 # 标题行
    text = md_text.split("<!-- INFO END -->")[-1]
    parts = [p.strip() for p in ARTICLE_RE.split(text) if p.strip()]
    articles = []
    for p in parts:
        m = re.match(r"^(第[一二三四五六七八九十百千零〇]+条)\s*", p)
        if not m:
            continue  # 跳过非条文段落（章标题等）
        art_no = m.group(1)
        body = p[m.end():].strip()
        # 条内多段合并为一段（保留句读，去多余空行）
        body = re.sub(r"\n+", "\n", body)
        if len(body) >= 15:
            articles.append((art_no, body))
    return articles


async def import_laws():
    from tortoise import Tortoise
    from app.models.law import Law

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law"]},
    )
    existing = await Law.filter(id__startswith="law_1").count()
    if existing > 0:
        print(f"法条已导入过（law_1* 存在 {existing} 条），跳过")
        await Tortoise.close_connections()
        return

    seq = 100
    total = 0
    for dir_name, pattern, display, category in LAW_SOURCES:
        fname = pattern if pattern.endswith(".md") else resolve_filename(dir_name, pattern)
        if fname is None:
            continue
        md = fetch_repo_file(f"{dir_name}/{fname}")
        if md is None:
            continue
        articles = split_articles(md)
        batch = []
        for art_no, body in articles:
            batch.append(Law(
                id=f"law_{seq}",
                title=f"{display} {art_no}",
                content=body,
                source=f"LawRefBook/Laws {dir_name}/{fname}",
                category=category,
                keywords=[display, category],
            ))
            seq += 1
        if batch:
            await Law.bulk_create(batch, ignore_conflicts=True)
            total += len(batch)
        print(f"[OK] {display}: {len(articles)} 条")
        time.sleep(0.6)
    print(f"法条导入完成: {total} 条")
    await Tortoise.close_connections()


# ── 案例导入 ──
CASE_DIRS = {
    "劳动人事": "劳动争议",
    "民法典": "民事",
    "消费购物": "民事",
    "行政协议诉讼": "行政",
}


def parse_case_md(md_text: str) -> dict:
    """解析案例 md：标题/各节内容/引用法条"""
    text = md_text.split("<!-- INFO END -->")[-1].strip()
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip() if lines else "未知标题"

    # 按二级标题切节
    sections = {}
    current = None
    buf: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif not line.startswith("#"):
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()

    # summary：基本案情 + 裁判结果（前 400 字）；content：全文
    summary_parts = []
    for key in ("基本案情", "裁判结果"):
        if key in sections:
            summary_parts.append(sections[key])
    summary = "\n".join(summary_parts)[:400] or text[:300]

    # 提取引用法条：《XXX法》第X条
    laws = sorted(set(f"《{m.group(1)}》" for m in LAW_CITE_RE.finditer(text)))

    return {
        "title": title[:200],
        "summary": summary,
        "content": text,
        "laws": laws,
    }


async def import_cases():
    from tortoise import Tortoise
    from app.models.case import Case

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.case"]},
    )
    total = 0
    for sub, case_type in CASE_DIRS.items():
        names = list_repo_dir(f"案例/{sub}")
        print(f"[{sub}] {len(names)} 个文件")
        for name in names:
            if not name.endswith(".md") or name == "_index.md":
                continue
            md = fetch_repo_file(f"案例/{sub}/{name}")
            if md is None:
                continue
            parsed = parse_case_md(md)
            if len(parsed["content"]) < 100:
                continue
            if await Case.filter(title=parsed["title"]).exists():
                continue
            await Case.create(
                title=parsed["title"],
                case_type=case_type,
                summary=parsed["summary"],
                content=parsed["content"],
                laws=parsed["laws"] or None,
                case_tags=[sub, "LawRefBook/Laws"],
            )
            total += 1
            time.sleep(0.6)
    print(f"案例导入完成: {total} 条")
    await Tortoise.close_connections()


async def main():
    print("=== 法条导入（按条粒度）===")
    await import_laws()
    print("\n=== 案例导入（典型案例全文）===")
    await import_cases()


if __name__ == "__main__":
    asyncio.run(main())
