# script to freeze the corpus at the latest commit on the default branch and write corpus.jsonl + CORPUS.md.

import os, json, base64
from pathlib import Path
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

REPOS_FILE = PROJECT_ROOT / "repos.txt"
OUT_JSONL = PROJECT_ROOT / "logs" / "corpus.jsonl"
OUT_MD = PROJECT_ROOT / "logs" / "CORPUS.md"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

def gh(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params or {})
    if r.status_code == 401:
        raise SystemExit("GitHub 401 Unauthorized. Set GITHUB_TOKEN to avoid this.")
    if r.status_code == 403:
        # likely rate limited
        raise SystemExit("GitHub 403 Forbidden (rate limit). Set GITHUB_TOKEN to continue.")
    if r.status_code >= 400:
        raise SystemExit(f"GitHub {r.status_code} on {url}: {r.text[:200]}")
    return r.json()

def load_repos():
    if not REPOS_FILE.exists():
        raise SystemExit(f"Missing {REPOS_FILE}. Put one owner/name per line.")
    with open(REPOS_FILE) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

def latest_on_default(repo):
    info = gh(f"https://api.github.com/repos/{repo}")
    license_spdx = (info.get("license") or {}).get("spdx_id") or "UNKNOWN"
    branch = info.get("default_branch") or "main"
    commits = gh(f"https://api.github.com/repos/{repo}/commits",
                 params={"sha": branch, "per_page": 1})
    if not commits:
        raise SystemExit(f"No commits found for {repo}@{branch}")
    c = commits[0]
    return license_spdx, c["sha"], c["commit"]["author"]["date"], branch

def fetch_package_json(repo, ref):
    # Try to read package.json at the given ref; if missing, return None.
    try:
        pj = gh(f"https://api.github.com/repos/{repo}/contents/package.json",
                params={"ref": ref})
    except SystemExit:
        return None
    if not isinstance(pj, dict) or "content" not in pj:
        return None
    try:
        raw = base64.b64decode(pj["content"]).decode("utf-8", errors="ignore")
        return json.loads(raw)
    except Exception:
        return None

def simple_curation(pj):
    """Very small heuristic: classify kind, detect tests, monorepo."""
    cur = {"kind": "unknown", "tests": False, "monorepo": False, "notes": []}
    if not pj:
        return cur

    name = (pj.get("name") or "").lower()
    scripts = pj.get("scripts") or {}
    deps = {**(pj.get("dependencies") or {}), **(pj.get("devDependencies") or {})}
    keywords = set((pj.get("keywords") or []))
    workspaces = "workspaces" in pj

    # tests
    test_signals = {"jest","vitest","mocha","ava","tap","uvu","playwright","cypress"}
    cur["tests"] = ("test" in scripts) or any(t in deps for t in test_signals)

    # monorepo
    cur["monorepo"] = bool(workspaces)

    # kind
    framework_signals = {
        "next","nuxt","sveltekit","nestjs","angular","remix","astro"
    }
    dep_names = set(deps.keys())
    if any(f in name for f in framework_signals) or any(
        f in dep_names or f in keywords for f in framework_signals
    ):
        cur["kind"] = "framework"
    elif pj.get("private") and any(k in scripts for k in ["start","dev","build"]):
        cur["kind"] = "app"
    else:
        cur["kind"] = "library"

    if cur["tests"]: cur["notes"].append("tests")
    if cur["monorepo"]: cur["notes"].append("monorepo")
    return cur

def main():
    repos = load_repos()
    rows = []

    for repo in repos:
        try:
            license_spdx, sha, date_iso, branch = latest_on_default(repo)
            pj = fetch_package_json(repo, sha)
            cur = simple_curation(pj)
            row = {
                "repo": repo,
                "commit_sha": sha,
                "commit_date": date_iso,
                "license_spdx": license_spdx,
                "curation": cur
            }
            rows.append(row)
            print(f"✔ {repo} @ {sha[:7]}  ({cur['kind']}, tests={str(cur['tests']).lower()}, mono={str(cur['monorepo']).lower()})")
        except SystemExit as e:
            print(f"✖ {repo}: {e}")
        except Exception as e:
            print(f"✖ {repo}: {type(e).__name__}: {e}")

    # Write JSONL
    with open(OUT_JSONL, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # Write markdown table
    with open(OUT_MD, "w") as f:
        f.write("# TypeScript Benchmark Corpus\n\n")
        f.write("_Frozen at latest commit on default branches (at script run time)._  \n")
        f.write("Columns: repo, short SHA, date, license, kind, tests?, monorepo?\n\n")
        f.write("| Repo | Commit | Date | License | Kind | Tests | Monorepo |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            c = r["curation"]
            f.write(f"| `{r['repo']}` | `{r['commit_sha'][:7]}` | {r['commit_date'][:10]} | {r['license_spdx']} | {c['kind']} | {str(c['tests']).lower()} | {str(c['monorepo']).lower()} |\n")

    print(f"\nWrote {OUT_JSONL} and {OUT_MD}")

if __name__ == "__main__":
    main()
