import os
import json
import subprocess
from pathlib import Path
from jsonc_parser.parser import JsoncParser
import re

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

# >>> NEW HELPER FUNCTION TO GET TYPE STRICTNESS DATA
def get_tsconfig_strictness(repo_dir: Path):
    """Reads tsconfig.json and extracts key compiler options for strictness."""
    
    # Search for tsconfig.json starting from the repository root
    # Note: This is a simple check; for complex monorepos, a recursive search might be needed.
    tsconfig_path = repo_dir / 'tsconfig.json'
    
    if not tsconfig_path.exists():
        return {}
    
    try:
        # Use JsoncParser to handle comments in tsconfig.json
        config = JsoncParser.parse_file(tsconfig_path)
        compilerOptions = config.get('compilerOptions', {})
        
        # Extract key strictness and optimization flags
        strictness = {
            "strict": compilerOptions.get('strict', False),
            "strictNullChecks": compilerOptions.get('strictNullChecks', False),
            "noImplicitAny": compilerOptions.get('noImplicitAny', False),
            "skipLibCheck": compilerOptions.get('skipLibCheck', False)
        }
        return strictness
    except Exception as e:
        print(f"[WARN] Could not parse tsconfig.json for {repo_dir.name}. Error: {e}")
        return {}
    
# >>> NEW HELPER FUNCTION TO GET DEPENDENCY GRAPH DEPTH (using npx madge)
def get_dependency_graph_depth(repo_dir: Path):
    """
    Uses madge to calculate dependency graph metrics (Node Count, a proxy for complexity).
    Requires Node.js and npx access in the environment.
    """
    try:
        # Command uses npx and madge with JSON output
        cmd = [
            "npx", 
            "--yes", 
            "-p", 
            "madge@latest", 
            "madge", 
            "--json", 
            "--file-extensions", "ts,tsx,js,jsx", 
            "--exclude", "^(node_modules|dist|build|coverage|out|test)", # Exclude common build/test dirs
            "."
        ]
        
        # Run madge and capture the output
        result = subprocess.run(
            cmd, 
            cwd=repo_dir, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        graph_data = json.loads(result.stdout)
        
        # Calculate the total number of unique modules (nodes) in the graph
        all_nodes = set(graph_data.keys())
        for deps in graph_data.values():
            for dep in deps:
                # Normalize dependency paths (madge output often uses relative paths)
                all_nodes.add(dep) 

        return {
            "module_count": len(all_nodes), # Total number of unique modules
        }
        
    except subprocess.CalledProcessError as e:
        # madge returns a non-zero exit code if it finds a circular dependency
        # We still want the output if possible, but for simplicity, we'll log the error.
        print(f"[WARN] madge failed for {repo_dir.name}. Error: {e.stderr.strip().splitlines()[-1]}")
        return {"error": "Madge execution failed"}
    except json.JSONDecodeError:
        print(f"[WARN] madge output for {repo_dir.name} was not valid JSON.")
        return {"error": "Madge output invalid"}
    except Exception as e:
        print(f"[WARN] General error running madge: {type(e).__name__}: {e}")
        return {"error": "General Madge error"}

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

                # >>> NEW CALL TO GET TSCONFIG DATA
                tsconfig_data = get_tsconfig_strictness(repo_dir)

                # >>> NEW CALL 2: Get Dependency Graph Data
                graph_data = get_dependency_graph_depth(repo_dir)

                # use CORPUS + LOC to create metadata
                metadata[repo] = {
                    "commit_sha": sha,
                    "commit_date": row.get("commit_date"),
                    "license_spdx": row.get("license_spdx"),
                    "curation": row.get("curation"),
                    "loc": loc,
                    "tsconfig_data": tsconfig_data, # <<< NEW METADATA KEY
                    "graph_data": graph_data, # <<< NEW METADATA KEY
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