#!/usr/bin/env python3
"""
repo-keeper · 仓库建模前测

用你自己的 GitHub 主号跑，量清楚"你的仓库里到底有多少可用信号"。

为什么要量
----------
README 讨论的对照组是"只用 GitHub 原生的 label / milestone 分组"。
但这个基线在不同仓上强弱差异极大 —— 公开项目实测从 0% 到 100% 都有。
**不知道自己的仓落在哪，就没法判断新方法相对基线是赚是亏。**

同样要量的还有：
  - issue / PR 正文密度  → 决定分层模型的第二层够不够厚
  - commit 标题的 #引用率 → 决定 commit↔issue 的原生连接点有多少
  - 决策文档命中        → 决定"跨类型连接"这条路通不通

用法
----
  export GH_TOKEN=ghp_xxx        # 或先 gh auth login
  python3 scripts/measure_repo.py                 # 量当前 token 可见的全部仓
  python3 scripts/measure_repo.py org/owner/repo ... # 只量指定的仓
  python3 scripts/measure_repo.py --json out.json  # 同时输出 JSON

只读。不写任何数据，不改任何仓。
"""

import json
import os
import re
import subprocess
import sys
import statistics
from concurrent.futures import ThreadPoolExecutor

GH = os.environ.get("GH_BIN", "gh")
BODY_MIN = 80          # 正文"有实质内容"的字符阈值
PER_PAGE = 50          # 每类对象的抽样条数
TIMEOUT = 60


# ---------- GitHub API 薄封装 ----------

def api(path):
    """REST 取 JSON；失败返回 [] 而不是抛异常（抽样失败不该中断整体）。"""
    try:
        r = subprocess.run(
            [GH, "api", path], capture_output=True, text=True, timeout=TIMEOUT
        )
        if r.returncode != 0:
            return []
        return json.loads(r.stdout)
    except Exception:
        return []


def gql(query, **vars_):
    """GraphQL 取 JSON。"""
    args = []
    for k, v in vars_.items():
        args += ["-F", f"{k}={v}"]
    try:
        r = subprocess.run(
            [GH, "api", "graphql", "-f", f"query={query}"] + args,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        return json.loads(r.stdout).get("data") or {}
    except Exception:
        return {}


# ---------- 正则 ----------

RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)      # issue/PR 模板占位
RE_ANY_REF      = re.compile(r"#\d+")                # #123 或 owner/repo#123
RE_ISSUE_URL    = re.compile(r"github\.com/\S+/issues/\d+")
RE_ADR_DIR      = re.compile(
    r"(^|/)(adr|adrs|decisions?|architecture-decision|rfcs?)($|/)", re.I)
RE_ADR_FILE     = re.compile(
    r"(^|/)(adr[-_]?\d+|ADR|DECISIONS?|决策[^/]*)\.mdx?$", re.I)
RE_ADR_NUM      = re.compile(r"^\d{3,4}-", re.I)      # 0001-xxx.md


# ---------- 各项测量 ----------

def measure_repo(slug):
    """slug 形如 'owner/name'。返回各项指标，失败返回 None。"""
    meta = api(f"repos/{slug}")
    if not isinstance(meta, dict) or "name" not in meta:
        return None

    labels = api(f"repos/{slug}/labels?per_page=100")
    issues_raw = api(f"repos/{slug}/issues?state=all&per_page={PER_PAGE}")
    prs_raw    = api(f"repos/{slug}/pulls?state=all&per_page={PER_PAGE}")
    commits    = api(f"repos/{slug}/commits?per_page={PER_PAGE}")
    tree       = api(f"repos/{slug}/git/trees/HEAD?recursive=1")

    issues = [x for x in issues_raw if isinstance(x, dict) and "pull_request" not in x]
    prs    = [x for x in prs_raw   if isinstance(x, dict)]
    commits = [c for c in commits if isinstance(c, dict)]

    def body_density(items, key="body"):
        lens = [
            len(RE_HTML_COMMENT.sub("", (it.get(key) or "")).strip())
            for it in items
        ]
        if not lens:
            return None
        return {
            "n": len(lens),
            "substantive": sum(1 for x in lens if x >= BODY_MIN),
            "median": int(statistics.median(lens)),
        }

    # commit 标题行是否引用了 #数字
    refs = 0
    for c in commits:
        msg = ((c.get("commit") or {}).get("message") or "")
        if RE_ANY_REF.search(msg.split("\n")[0]):
            refs += 1

    # 决策文档 / ADR
    adr_hits, md_count, truncated = [], 0, False
    if isinstance(tree, dict) and "tree" in tree:
        truncated = tree.get("truncated", False)
        for t in tree["tree"]:
            p = t.get("path", "")
            if t.get("type") == "blob" and p.lower().endswith((".md", ".mdx", ".rst")):
                md_count += 1
                if (RE_ADR_DIR.search(p) or RE_ADR_FILE.search(p)
                        or RE_ADR_NUM.match(p.split("/")[-1])):
                    adr_hits.append(p)

    return {
        "repo": slug,
        "private": meta.get("private", False),
        "created": (meta.get("created_at") or "")[:10],
        "pushed":  (meta.get("pushed_at")  or "")[:10],
        "issue_open":   meta.get("open_issues_count", 0),   # 注意：GitHub 该字段含 PR
        "issue_total":  len(issues),
        "pr_total":     len(prs),
        "pr_merged":    sum(1 for p in prs if p.get("merged_at")),
        "labels_defined": len(labels) if isinstance(labels, list) else 0,
        "issue_with_label":  sum(1 for i in issues  if i.get("labels")),
        "issue_with_milestone": sum(1 for i in issues if i.get("milestone")),
        "pr_with_label":  sum(1 for p in prs if p.get("labels")),
        "pr_with_milestone": sum(1 for p in prs if p.get("milestone")),
        "issue_body": body_density(issues),
        "pr_body":    body_density(prs),
        "commit_sampled": len(commits),
        "commit_with_ref": refs,
        "md_files": md_count,
        "adr_hits": len(adr_hits),
        "adr_examples": adr_hits[:5],
        "tree_truncated": truncated,
    }


# ---------- 发现可测量的仓 ----------

Q_REPOS = """
query($login:String!){
  viewer{ login }
  u:user(login:$login){ repositories(first:100,orderBy:{field:PUSHED_AT,direction:DESC}){ nodes{ nameWithOwner isPrivate } } }
  o:organization(login:$login){ repositories(first:100,orderBy:{field:PUSHED_AT,direction:DESC}){ nodes{ nameWithOwner isPrivate } } }
}
"""


def discover(login):
    """列出该 user / org 名下当前 token 可见的全部仓。"""
    d = gql(Q_REPOS, login=login) or {}
    out = []
    for branch in ("u", "o"):
        node = (d.get(branch) or {})
        for r in (node.get("repositories") or {}).get("nodes", []) or []:
            if r:
                out.append(r["nameWithOwner"])
    return sorted(set(out))


# ---------- 输出 ----------

def pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "—"


def print_table(rows):
    print(f"\n{'仓库':38}{'iss':>6}{'PR':>5}{'PR并':>6}{'lb定义':>8}"
          f"{'PR带lb':>9}{'PR带ms':>9}{'iss正文':>9}{'PR正文':>8}{'#引用':>8}{'ADR':>5}")
    print("-" * 118)
    agg = {k: 0 for k in ("issue_total", "pr_total", "pr_merged", "labels_defined",
                          "pr_with_label", "pr_with_milestone", "issue_with_label",
                          "commit_sampled", "commit_with_ref", "adr_hits",
                          "iss_sub", "iss_n", "pr_sub", "pr_n")}
    for r in rows:
        ib = r["issue_body"] or {}
        pb = r["pr_body"] or {}
        iss_b = pct(ib.get("substantive", 0), ib.get("n", 0))
        pr_b  = pct(pb.get("substantive", 0), pb.get("n", 0))
        ref   = pct(r["commit_with_ref"], r["commit_sampled"])
        print(f"{r['repo']:38}{r['issue_total']:>6}{r['pr_total']:>5}{r['pr_merged']:>6}"
              f"{r['labels_defined']:>8}{pct(r['pr_with_label'], r['pr_total']):>9}"
              f"{pct(r['pr_with_milestone'], r['pr_total']):>9}{iss_b:>9}{pr_b:>8}{ref:>8}{r['adr_hits']:>5}")
        for k in ("issue_total", "pr_total", "pr_merged", "labels_defined",
                  "pr_with_label", "pr_with_milestone", "issue_with_label",
                  "commit_sampled", "commit_with_ref", "adr_hits"):
            agg[k] += r[k]
        agg["iss_sub"] += ib.get("substantive", 0); agg["iss_n"] += ib.get("n", 0)
        agg["pr_sub"]  += pb.get("substantive", 0); agg["pr_n"]  += pb.get("n", 0)
    print("-" * 118)
    print(f"合计 issue={agg['issue_total']}  PR={agg['pr_total']}（并 {agg['pr_merged']}）  "
          f"labels定义={agg['labels_defined']}")
    print(f"  PR 带 label      : {pct(agg['pr_with_label'], agg['pr_total'])}")
    print(f"  PR 带 milestone  : {pct(agg['pr_with_milestone'], agg['pr_total'])}")
    print(f"  issue 正文密度   : {pct(agg['iss_sub'], agg['iss_n'])}"
          f"  （阈值 {BODY_MIN} 字符，样本 {agg['iss_n']}）")
    print(f"  PR   正文密度    : {pct(agg['pr_sub'], agg['pr_n'])}"
          f"  （样本 {agg['pr_n']}）")
    print(f"  commit 标题 #引用: {pct(agg['commit_with_ref'], agg['commit_sampled'])}"
          f"  （样本 {agg['commit_sampled']}）")
    print(f"  决策文档 / ADR   : {agg['adr_hits']} 个")

    trunc = [r["repo"] for r in rows if r["tree_truncated"]]
    if trunc:
        print(f"\n  ⚠️ 以下仓的目录树被 GitHub 截断，ADR 结论可能有假阴性：{', '.join(trunc)}")

    # 关键判读
    print("\n" + "=" * 118)
    print("怎么读这组数")
    print("=" * 118)
    print(f"""  ① PR 带 label {pct(agg['pr_with_label'], agg['pr_total'])}
     → 原生基线的水平。>60% 说明基线强，新方法增益小、验证难；
       <20% 说明基线近乎无效，新方法有充足空间。
  ② issue 正文密度 {pct(agg['iss_sub'], agg['iss_n'])} · PR 正文 {pct(agg['pr_sub'], agg['pr_n'])}
     → 分层模型第二层的厚度。<50% 意味着"下钻看正文"这条路走不通。
  ③ commit 标题 #引用 {pct(agg['commit_with_ref'], agg['commit_sampled'])}
     → commit↔issue 原生连接点的密度。低则图会碎成孤岛。
  ④ 决策文档 {agg['adr_hits']} 个
     → 跨类型连接这条路通不通。0 个则该功能在你的仓上无法验证。
  ⑤ issue 总数 {agg['issue_total']}
     → 如果这个数很低（个位数），README 第四节"节点与边"里的 issue 维度
       在你的仓上就没有数据，模型要按 commit+PR 重新设计主干。""")


USAGE = """\
用法：
  python3 scripts/measure_repo.py <user|org>          测该账号下全部可见的仓
  python3 scripts/measure_repo.py <owner/name> [...]  测指定的仓
  python3 scripts/measure_repo.py <owner/name> --json <输出文件>
  python3 scripts/measure_repo.py                     交互式询问账号名

前置：
  · gh CLI 已登录（gh auth login）
  · **用你自己的主号**，不要用 agent 沙盘小号 ——
    小号的数据跟主号是完全两批，结论会整个反过来

输出六项：PR label 覆盖率 / issue·PR 正文密度 /
          commit 标题 #引用率 / 决策文档命中 / milestone 覆盖率 / 分支信号
"""


def main():
    args = sys.argv[1:]

    # --help / -h：不连 API，直接打用法（连 API 之前就退，
    # 免得用户只是想看用法却因为 token 问题报错）
    if "-h" in args or "--help" in args:
        print(USAGE)
        return

    as_json = None
    if "--json" in args:
        i = args.index("--json")
        if i + 1 >= len(args):
            print("--json 后面要跟输出文件名")
            print(USAGE)
            sys.exit(1)
        as_json = args[i + 1]
        args = args[:i] + args[i + 2:]

    viewer = (gql("query{viewer{login}}") or {}).get("viewer", {}).get("login", "?")
    print(f"当前 token 身份：{viewer}")
    print("（如果这是 agent 沙盘小号，测出来的不是你的工作模式，请换主号重跑）")

    # 位置参数：含 "/" 视为 owner/name 仓名；不含 "/" 视为 user/org 名，自动发现其下全部仓
    slugs = [a for a in args if "/" in a]
    accounts = [a for a in args if "/" not in a]
    if accounts and slugs:
        print("参数混用了账号名和 owner/name，请二选一。")
        sys.exit(1)

    if accounts:
        login = accounts[0]
        slugs = discover(login)
        if not slugs:
            print(f"没在 {login} 下发现可见的仓。检查 token 权限。")
            sys.exit(1)
        print(f"\n{login} 下发现 {len(slugs)} 个仓，开始测量…")
    elif not slugs:
        login = input("\n量哪个账号？输入 user 或 org 名：").strip()
        slugs = discover(login)
        if not slugs:
            print("没发现可见的仓。检查 token 权限，或直接用 'owner/name' 形式指定。")
            sys.exit(1)
        print(f"发现 {len(slugs)} 个仓：{', '.join(slugs)}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(measure_repo, slugs) if r]
    if not rows:
        print("没有成功测到任何仓。")
        sys.exit(1)

    print_table(rows)

    if as_json:
        with open(as_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 已写入：{as_json}  ← 可以直接贴回来给我分析")


if __name__ == "__main__":
    main()
