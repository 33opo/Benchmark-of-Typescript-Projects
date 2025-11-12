import os
import json
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# === CONFIG ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
BASE_DIR = PROJECT_ROOT / "projects"
LOG_FILE = PROJECT_ROOT / "skipped_projects.log"
CORPUS = PROJECT_ROOT / "logs" / "corpus.jsonl"
LOGS_DIR = PROJECT_ROOT / "logs"
METADATA_FILE = PROJECT_ROOT / "logs" / "metadata.json"
REPOS_FILE = PROJECT_ROOT / "repos.txt"
EXCLUDE_DIRS = {".git", "node_modules", "dist", "build", ".next", "out", "coverage", ".venv", "venv"}
EXCLUDE_FILE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".svg", ".ico", ".zip", ".gz", ".rar", ".7z"}
TS_EXTS = {".ts", ".tsx"}
JS_EXTS = {".js", ".jsx"}
OTHER_CODE_EXTS = {
    ".py",".java",".go",".rs",".c",".cc",".cpp",".h",".hh",".hpp",
    ".cs",".kt",".swift",".rb",".php",".m",".mm",".scala",".lua",
    ".dart",".sh",".bash",".zsh",".ps1",".r",".pl",".sql",".vue"
}
MAX_FILE_BYTES = 10 * 1024 * 1024 # 10 MB

# === HELPER FUNCTIONS ===

def count_loc_by_language(repo_dir):
    """Count lines of code by language in the given repository directory."""
    repo_dir = Path(repo_dir)
    totals = {"typescript": 0, "javascript": 0, "other": 0}

    for root, dirs, files in os.walk(repo_dir):
        # get all directories except for the big ones we want to skip
        dirs[:] = [directory for directory in dirs if directory not in EXCLUDE_DIRS]

        for filename in files:
            p = Path(root) / filename
            type = p.suffix.lower()

            # skip obvious non-code or huge files
            if type in EXCLUDE_FILE_EXTS:
                continue
            try:
                # skip files that go over our size limit
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except Exception:
                continue

            # check what type of code file it is
            if type in TS_EXTS or filename.lower().endswith(".d.ts"):
                codeType = "typescript"
            elif type in JS_EXTS:
                codeType = "javascript"
            elif type in OTHER_CODE_EXTS:
                codeType = "other"
            else:
                continue

            # count all the actual code lines in the file
            try:
                with open(p, "r", errors="ignore") as fh:
                    n = sum(1 for line in fh if line.strip())
                totals[codeType] += n
            except Exception:
                continue

    totals["total"] = totals["typescript"] + totals["javascript"] + totals["other"]
    return totals

def sh(*args, cwd=None):
    """wrapper for subprocess.check_call."""
    subprocess.check_call(list(args), cwd=cwd)

def clone_or_checkout(repo_full: str, sha: str):
    """Ensure a working tree exists at projects/<name> and is checked out to `sha`."""
    owner, name = repo_full.split("/")
    dest = BASE_DIR / name
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # clone if the folder of the project does not exist
    if not dest.exists():
      sh("git", "clone", "--filter=blob:none", f"https://github.com/{repo_full}.git", str(dest))

    # Make sure we have up-to-date references, then checkout the exact commit.
    sh("git", "fetch", "--all", "--tags", "--prune", cwd=dest)
    sh("git", "checkout", "-q", sha, cwd=dest)

def main():
    # creates directory if not exists, need CORPUS file to run this script
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not CORPUS.exists():
        raise SystemExit(f"Missing corpus file: {CORPUS}. Run freeze_corpus.py first.")

    metadata = {}

    with open(CORPUS) as f:
        for line in f:
            # go through CORPUS file and get info
            row = json.loads(line)
            repo = row["repo"]
            sha = row["commit_sha"]
            print(f"[checkout] {repo} @ {sha[:7]}")

            try:
                clone_or_checkout(repo, sha)

                # compute LOC
                repo_dir = BASE_DIR / repo.split("/")[1]
                loc = count_loc_by_language(repo_dir)

                # use CORPUS + LOC to create metadata
                metadata[repo] = {
                    "commit_sha": sha,
                    "commit_date": row.get("commit_date"),
                    "license_spdx": row.get("license_spdx"),
                    "curation": row.get("curation"),
                    "loc": loc,
                }
            except subprocess.CalledProcessError as e:
                print(f"[WARN] git failed for {repo}: {e}")
            except Exception as e:
                print(f"[WARN] error for {repo}: {type(e).__name__}: {e}")

    # write the metadata file
    with open(METADATA_FILE, "w") as out:
        json.dump(metadata, out, indent=2)
    print(f"[ok] wrote {METADATA_FILE}")

if __name__ == "__main__":
    main()