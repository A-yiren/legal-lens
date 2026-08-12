#!/usr/bin/env python3
"""
抓取官方法律文本 → 生成结构化 .md (Phase 2 - 官方源)

URL 全部使用可访问的官方/政府/稳定镜像：
- 人民网 / 共产党员网 / 中国人大网 / 中国妇女网 / 地方人大
- 网易（new.qq.com 企鹅号）/ 搜狐（sohu.com）/ 法大大 / 律图网
- 河南省人社厅 / 黑龙江省知识产权局 / 福建省药监 / 山东法院 / 佛山顺德政府
- 威驰外资企业服务网 (waizi.org.cn) / idataserch.com
- 搜狗律师 (lvshi.sogou.com) / 衡水学院学报

支持类型：
- html: requests + BeautifulSoup + lxml
- pdf: pypdf
- docx: python-docx
- doc: 通过 antiword/soffice 转换（不可用时跳过）
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib3
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


# 26 部法律 - 全部使用稳定可访问的官方源 / 政府源 / 稳定镜像
# 格式: (file_name, law_name, url, publisher, version, ftype)
LAWS = [
    # ==================== 民法典 (cnwomen 转载新华社 - 2020-06-02) ====================
    ("民法典.md", "中华人民共和国民法典", "http://www.cnwomen.com.cn/2020/06/02/99199031.html", "中国妇女网（转载新华社）", "2020-05-28通过，2021-01-01施行", "html"),

    # ==================== 核心法律 ====================
    ("刑法.md", "中华人民共和国刑法", "https://www.gzzzb.gov.cn/ztzl/pfxc/20221117/20221117_669792.shtml", "贵阳组工（转载共产党员网）", "1979年制定，2017年第三次修正", "html"),
    ("个人信息保护法.md", "中华人民共和国个人信息保护法", "http://society.people.com.cn/n1/2021/0823/c1008-32202785.html", "人民网（来源：人民日报）", "2021-08-20通过，2021-11-01施行，主席令第91号", "html"),
    ("产品质量法.md", "中华人民共和国产品质量法", "http://www.npc.gov.cn/zgrdw/npc/xinwen/2019-01/07/content_2070255.htm", "中国人大网", "1993年制定，2018年修正", "html"),
    ("仲裁法.md", "中华人民共和国仲裁法", "http://hbj.anyang.gov.cn/2021/12-07/2289840.html", "安阳市生态环境局（转载2017修正）", "1994年制定，2017年第二次修正，2018-01-01施行", "html"),

    # ==================== 行政法 ====================
    ("行政许可法.md", "中华人民共和国行政许可法", "https://ypjg.ln.gov.cn/ypjg/zfxxgk/fdzdgknr/lzyj/xzfg/2022052810240554690/index.shtml", "辽宁省药监局", "2003年制定，2019年修正", "html"),
    ("行政强制法.md", "中华人民共和国行政强制法", "http://tjj.suzhou.gov.cn/sztjj/flfg/202004/1568dee696e8468abd645f7cdae89200.shtml", "苏州市统计局（转载中国政府网）", "2011-06-30通过，2012-01-01施行，主席令第49号", "html"),
    ("行政处罚法.md", "中华人民共和国行政处罚法", "https://www.sohu.com/a/446965813_120207504", "搜狐转载（2021修订）", "2021-01-22修订，2021-07-15施行，主席令第70号", "html"),
    ("行政诉讼法.md", "中华人民共和国行政诉讼法", "http://hrss.yn.gov.cn/NewsView.aspx?pid=971&nid=23809&cid=682&isZt=7", "云南省人社厅（2017修正）", "1989年制定，2017年第二次修正，主席令第71号", "html"),

    # ==================== 网络与数据三法 ====================
    ("网络安全法.md", "中华人民共和国网络安全法", "https://www.sohu.com/a/143313127_757346", "搜狐（7章79条全文）", "2016-11-07通过，2017-06-01施行", "html"),
    ("反垄断法.md", "中华人民共和国反垄断法", "https://fgw.sh.gov.cn/cmsres/82/82e396b3cff74f92a31e22573e90c2cf/bd82cb3c67b6f4e5c1300110368d7a29.pdf", "上海市发改委", "2022-06-24修订，2022-08-01施行，主席令第94号", "pdf"),
    ("数据安全法.md", "中华人民共和国数据安全法", "https://new.qq.com/rain/a/20250820A07VG700", "腾讯网（转载新华社）", "2021-06-10通过，2021-09-01施行", "html"),

    # ==================== 交通 ====================
    ("道路交通安全法.md", "中华人民共和国道路交通安全法", "https://www.waizi.org.cn/doc/111374.html", "威驰外资企业服务网（2021修正）", "2003年制定，2021年修正", "html"),

    # ==================== 商事/竞争 ====================
    ("反不正当竞争法.md", "中华人民共和国反不正当竞争法", "https://new.qq.com/rain/a/20250913A0642P00", "腾讯网", "2025-06-27通过，2025-10-15施行", "html"),
    ("商标法.md", "中华人民共和国商标法", "http://www.npc.gov.cn/npc/c2/c30834/202606/t20260626_455832.html", "中国人大网（2026-06-26修订）", "2026-06-26修订，2027-01-01施行，主席令第77号", "html"),
    ("公司法.md", "中华人民共和国公司法", "https://www.chinanews.com.cn/gn/2023/12-30/10137987.shtml", "中新网（2023修订）", "2023-12-29修订，2024-07-01施行，主席令第15号", "html"),

    # ==================== 劳动 ====================
    ("劳动合同法.md", "中华人民共和国劳动合同法", "http://www.64365.com/zs/638961.aspx", "律图网", "2007年制定，2012年修正", "html"),
    ("劳动法.md", "中华人民共和国劳动法", "https://www.12371.cn/2020/06/18/ARTI1592415044828445.shtml", "共产党员网（2018修正）", "1994年制定，2018年修正", "html"),
    ("劳动争议调解仲裁法.md", "中华人民共和国劳动争议调解仲裁法", "http://www.shunde.gov.cn/fssdrsj/attachment/0/323/323818/5572758.pdf", "佛山顺德政府（2007通过）", "2007-12-29通过，2008-05-01施行，主席令第80号", "pdf"),

    # ==================== 三大诉讼法 ====================
    ("刑事诉讼法.md", "中华人民共和国刑事诉讼法", "https://www.waizi.org.cn/doc/43388.html", "威驰外资企业服务网（2018修正）", "1979年制定，2018年第三次修正", "html"),
    ("民事诉讼法.md", "中华人民共和国民事诉讼法", "https://www.fadada.com/notice/detail-20915.html", "法大大（2023修正）", "2023-09-01第五次修正，2024-01-01施行", "html"),

    # ==================== 律师 + 保险 + 消费者 + 知识产权 ====================
    ("律师法.md", "中华人民共和国律师法", "https://lvshi.sogou.com/regulations/detail/7OGS6TWM1WE3.html", "搜狗律师（2012修正）", "1996年制定，2012年修正，主席令第64号", "html"),
    ("保险法.md", "中华人民共和国保险法", "https://idataserch.com/docs/zhong-hua-ren-min-gong-he-guo-bao-xian-fa-2015-nian-xiu-ding-ban", "idataserch.com（2015修正）", "1995年制定，2015年修正，183条", "html"),
    ("消费者权益保护法.md", "中华人民共和国消费者权益保护法", "https://lvshi.sogou.com/article/detail/7PCBVOG9NNMF.html", "搜狗律师（2013修正）", "1993年制定，2013年修正，2014-03-15施行，主席令第7号", "html"),
    ("著作权法.md", "中华人民共和国著作权法", "https://hlipa.hlj.gov.cn/hlipa/c103159/202111/c00_31316463.shtml", "黑龙江省知识产权局（2020修正）", "1990年制定，2020年第三次修正，2021-06-01施行，主席令第62号", "html"),
    ("专利法.md", "中华人民共和国专利法", "https://www.cnipa.gov.cn/art/2020/11/23/art_97_155167.html", "国家知识产权局（转载中国人大网）", "1984年制定，2020年第四次修正，2021-06-01施行", "html"),
]


def http_get(url, retries=3, timeout=30, verify=True):
    """HTTP GET with retries"""
    last_err = None
    for i in range(retries):
        try:
            headers = {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=verify)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last_err = e
            print(f"  retry {i+1}: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(2 ** i)
    return None


def extract_text_from_html(html_bytes, url):
    """从 HTML 提取正文文本"""
    if not html_bytes:
        return ""
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception:
        soup = BeautifulSoup(html_bytes, "html.parser")

    # 移除无用元素
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "header", "footer", "aside", "form", "button", "ins", "link"]):
        tag.decompose()

    # 尝试多个选择器找正文
    content = None
    for selector in [
        "article",
        "main",
        "div.article",
        "div.article-content",
        "div.article_content",
        "div.content",
        "div.TRS_Editor",
        "div[class*='content']",
        "div[id*='content']",
        "div[class*='article']",
        "div[id*='article']",
        "div[class*='law']",
        "div[class*='Law']",
        "div.main",
        "div.body",
        "div.text",
        "div#zoom",
        "div#lawContent",
        "td.content",
    ]:
        found = soup.select(selector)
        if found:
            content = max(found, key=lambda el: len(el.get_text(strip=True)))
            if len(content.get_text(strip=True)) > 1000:
                break

    if not content or len(content.get_text(strip=True)) < 1000:
        body = soup.find("body") or soup
        divs = body.find_all("div")
        if divs:
            content = max(divs, key=lambda el: len(el.get_text(strip=True)))
        else:
            content = body

    lines = []
    seen = set()
    for p in content.find_all(["p", "div", "li", "td", "h1", "h2", "h3", "h4", "h5", "h6"]):
        text = p.get_text(separator="\n", strip=True)
        if not text or text in seen:
            continue
        if len(text) < 8 and not p.name.startswith("h"):
            continue
        seen.add(text)
        lines.append(text)

    full_text = "\n\n".join(lines)
    if len(full_text) < 500:
        full_text = content.get_text(separator="\n", strip=True)
    return full_text


def extract_text_from_pdf(url):
    """从 PDF 提取文本"""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("  pypdf not installed", file=sys.stderr)
        return None

    pdf_bytes = http_get(url)
    if not pdf_bytes:
        return None

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        lines = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines.append(text)
        return "\n\n".join(lines)
    except Exception as e:
        print(f"  PDF parse error: {e}", file=sys.stderr)
        return None


def extract_text_from_docx(url):
    """从 DOCX 提取文本"""
    try:
        from docx import Document
    except ImportError:
        print("  python-docx not installed", file=sys.stderr)
        return None

    doc_bytes = http_get(url)
    if not doc_bytes:
        return None

    try:
        doc = Document(BytesIO(doc_bytes))
        lines = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(lines)
    except Exception as e:
        print(f"  DOCX parse error: {e}", file=sys.stderr)
        return None


def clean_text(text):
    """清理文本"""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r'第\s*\d+\s*页\s*共\s*\d+\s*页', '', text)
    text = re.sub(r'-\s*\d+\s*-', '', text)
    # 删除"北大法宝"/"原文链接"等水印
    text = re.sub(r'©\s*北大法宝.*?专业提供.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'原文链接[：:].*?$', '', text, flags=re.MULTILINE)
    return text.strip()


def extract_metadata_from_text(text, law_name):
    """提取元数据"""
    meta = {}
    head = text[:3000]
    m = re.search(r'主席令第[零一二三四五六七八九十百]+号', head)
    if m:
        meta['decree'] = m.group()
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日.*?(?:通过|修订|修正)', head)
    if m:
        meta['enact_date'] = f"{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*起?\s*施行', head)
    if m:
        meta['effective_date'] = f"{m.group(1)}年{m.group(2)}月{m.group(3)}日施行"
    return meta


def format_articles(text):
    """格式化为带章节/条文的 markdown"""
    text = re.sub(
        r'^(第[零一二三四五六七八九十百千万亿〇\d]+条[之]?)',
        r'**\1**',
        text,
        flags=re.MULTILINE
    )
    text = re.sub(
        r'^(第[零一二三四五六七八九十百千万]+章\s*[^\n]+)',
        r'## \1',
        text,
        flags=re.MULTILINE
    )
    text = re.sub(
        r'^(第[零一二三四五六七八九十百千万]+节\s*[^\n]+)',
        r'### \1',
        text,
        flags=re.MULTILINE
    )
    return text


def build_markdown(file_name, law_name, url, publisher, version, raw_text, meta):
    """构造最终的 .md"""
    domain = urlparse(url).netloc

    frontmatter = f"""---
source_url: {url}
source_domain: {domain}
scraped_at: {datetime.now().strftime('%Y-%m-%d')}
publisher: {publisher}
law_status: {version}
original_law_name: {law_name}
"""
    if meta.get('decree'):
        frontmatter += f"decree: {meta['decree']}\n"
    if meta.get('enact_date'):
        frontmatter += f"enact_date: {meta['enact_date']}\n"
    if meta.get('effective_date'):
        frontmatter += f"effective_date: {meta['effective_date']}\n"
    frontmatter += "---\n\n"

    head = f"# {law_name}\n\n"
    head += f"> **官方源链接**：[{domain}]({url})\n"
    head += f"> **转载来源**：{publisher}\n"
    head += f"> **版本说明**：{version}\n"
    if meta.get('decree'):
        head += f"> **主席令**：{meta['decree']}\n"
    if meta.get('enact_date'):
        head += f"> **通过日期**：{meta['enact_date']}\n"
    if meta.get('effective_date'):
        head += f"> **施行日期**：{meta['effective_date']}\n"
    head += f"> **抓取时间**：{datetime.now().strftime('%Y-%m-%d')}\n\n"

    body = format_articles(raw_text)
    return frontmatter + head + body + "\n"


def main():
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/seed_data_official")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, (file_name, law_name, url, publisher, version, ftype) in enumerate(LAWS, 1):
        print(f"\n[{i}/{len(LAWS)}] {law_name} ({ftype})")
        print(f"  URL: {url}")

        t0 = time.time()
        if ftype == "html":
            raw = http_get(url)
            text = extract_text_from_html(raw, url) if raw else None
        elif ftype == "pdf":
            text = extract_text_from_pdf(url)
        elif ftype == "docx":
            text = extract_text_from_docx(url)
        elif ftype == "doc":
            text = None  # doc support not implemented; need soffice
            print(f"  ✗ .doc not supported without soffice/antiword, skip", file=sys.stderr)
        else:
            text = None

        if not text or len(text) < 200:
            print(f"  ✗ 失败 (text={len(text) if text else 0} 字符)")
            results.append({"file_name": file_name, "law_name": law_name, "status": "failed", "chars": len(text) if text else 0, "url": url, "ftype": ftype})
            continue

        text = clean_text(text)
        meta = extract_metadata_from_text(text, law_name)
        md = build_markdown(file_name, law_name, url, publisher, version, text, meta)
        out_path = output_dir / file_name
        out_path.write_text(md, encoding="utf-8")
        elapsed = time.time() - t0
        print(f"  ✓ {len(text)} 字符, {len(md)} bytes, {elapsed:.1f}s")
        print(f"    元数据: {meta}")
        print(f"    含「第X条」: {('第一条' in text)}, 含「第X章」: {('第一章' in text)}")
        results.append({"file_name": file_name, "law_name": law_name, "status": "ok", "chars": len(text), "elapsed": elapsed, "url": url, "ftype": ftype, "meta": meta})

        time.sleep(0.5)

    with open(output_dir / "_index.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok_count = sum(1 for r in results if r["status"] == "ok")
    total_chars = sum(r.get("chars", 0) for r in results)
    print(f"\n=== 完成 {ok_count}/{len(results)} 部, 总 {total_chars:,} 字符 ===")
    print(f"=== 输出目录: {output_dir} ===")
    return ok_count == len(results)


if __name__ == "__main__":
    main()
