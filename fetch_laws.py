#!/usr/bin/env python3
"""从全国人大法律法规库 (flk.npc.gov.cn) 拉中国主要法律
返回结构化 JSON
"""
import json
import re
import time
import urllib.request
import urllib.parse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

LAWS = [
    # 民法典 7 编
    ("中华人民共和国民法典", "mfd-total"),  # 总则编
    ("中华人民共和国民法典", "mfd-wq"),     # 物权编
    # 合同编已有
    ("中华人民共和国民法典", "mfd-rgq"),    # 人格权编
    ("中华人民共和国民法典", "mfd-hyjt"),   # 婚姻家庭编
    ("中华人民共和国民法典", "mfd-jc"),     # 继承编
    ("中华人民共和国民法典", "mfd-wqzr"),   # 侵权责任编
    # 刑法
    ("中华人民共和国刑法", "criminal-law"),
    # 三大诉讼法
    ("中华人民共和国民事诉讼法", "cpl"),
    ("中华人民共和国行政诉讼法", "apl"),
    ("中华人民共和国刑事诉讼法", "crm-law"),
    # 商事
    ("中华人民共和国公司法", "company-law"),
    ("中华人民共和国证券法", "securities-law"),
    ("中华人民共和国反不正当竞争法", "anti-unfair-competition"),
    ("中华人民共和国反垄断法", "anti-monopoly-law"),
    # 劳动
    ("中华人民共和国劳动法", "labor-law"),
    # 劳动合同法已有
    ("中华人民共和国劳动争议调解仲裁法", "labor-dispute"),
    # 知识产权
    # 专利法已有
    ("中华人民共和国商标法", "trademark-law"),
    ("中华人民共和国著作权法", "copyright-law"),
    # 消费者
    ("中华人民共和国消费者权益保护法", "consumer-rights"),
    ("中华人民共和国产品质量法", "product-quality"),
    # 行政法
    ("中华人民共和国行政处罚法", "admin-penalty"),
    ("中华人民共和国行政许可法", "admin-license"),
    ("中华人民共和国行政强制法", "admin-coercion"),
    # 仲裁/律师
    ("中华人民共和国仲裁法", "arbitration"),
    ("中华人民共和国律师法", "lawyer-law"),
    # 数据三法
    ("中华人民共和国数据安全法", "data-security"),
    ("中华人民共和国个人信息保护法", "pipl"),
    ("中华人民共和国网络安全法", "cybersecurity"),
    # 交通
    ("中华人民共和国道路交通安全法", "traffic-safety"),
    # 保险
    ("中华人民共和国保险法", "insurance-law"),
]


def http_get(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://flk.npc.gov.cn/",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  retry {i+1}: {e}")
            time.sleep(2)
    return None


def search_law(keyword, size=5):
    kw = urllib.parse.quote(keyword)
    url = f"https://flk.npc.gov.cn/api/?searchType=title&keyword={kw}&size={size}&page=1"
    return http_get(url)


def main():
    results = {}
    for title, slug in LAWS:
        print(f"\n[{slug}] {title}")
        # 先搜 1 个
        body = search_law(title, size=3)
        if not body:
            print("  failed to search")
            results[slug] = {"title": title, "error": "search failed"}
            continue
        try:
            data = json.loads(body)
        except Exception as e:
            print(f"  JSON parse failed: {e}")
            print(f"  raw: {body[:200]}")
            results[slug] = {"title": title, "error": "json parse", "raw": body[:200]}
            continue
        items = data.get("data", {}).get("resultData", []) or []
        if not items:
            print(f"  no result, body: {body[:200]}")
            results[slug] = {"title": title, "error": "no result"}
            continue
        # 选第一个
        law = items[0]
        print(f"  found: {law.get('title', '?')[:50]}")
        results[slug] = {
            "title": title,
            "npc_id": law.get("id"),
            "npc_url": "https://flk.npc.gov.cn/detail2.html?" + law.get("url", ""),
        }
        time.sleep(1)
    # 输出
    with open("/tmp/laws_index.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n=== 写入 /tmp/laws_index.json, 共 {len(results)} 部 ===")


if __name__ == "__main__":
    main()
