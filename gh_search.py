"""找中国法律数据 GitHub 仓库"""
import urllib.request
import json

queries = [
    "中国法律",
    "law-cn chinese",
    "flk npc law",
    "民法典 刑法",
]

for q in queries:
    qe = urllib.request.quote(q)
    url = f"https://api.github.com/search/repositories?q={qe}&sort=stars&per_page=8"
    req = urllib.request.Request(url, headers={
        "User-Agent": "curl",
        "Accept": "application/vnd.github+json",
    })
    try:
        r = urllib.request.urlopen(req, timeout=15)
        d = json.loads(r.read())
        print(f"\n=== Query: {q} ===")
        for item in d.get("items", [])[:6]:
            stars = item.get("stargazers_count", 0)
            name = item.get("full_name", "")
            desc = (item.get("description") or "")[:60]
            print(f"  {stars:>5} {name:<45} | {desc}")
    except Exception as e:
        print(f"  ERR {q}: {e}")
