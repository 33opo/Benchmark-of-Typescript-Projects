import os
import json
import requests
from datetime import datetime, timedelta
from git import Repo
from dotenv import load_dotenv

# Load environment variables from .env file (safe, ignored by git)
load_dotenv()

# === CONFIG ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
BASE_DIR = "projects"
LOG_FILE = "skipped_projects.log"
METADATA_FILE = "./logs/metadata.json"
REPOS_FILE = "repos.txt"

# === HELPER FUNCTIONS ===

def load_repos(file_path):
    """Load repository names from a text file."""
    if not os.path.exists(file_path):
        print(f"[ERROR] Repos file '{file_path}' does not exist.")
        return []
    with open(file_path, "r") as f:
        repos = [line.strip() for line in f if line.strip()]
    return repos


def get_recent_commit(repo_name):
    """Return the SHA and date of the latest commit within the last year."""
    last_year = datetime.now() - timedelta(days=365)
    url = f"https://api.github.com/repos/{repo_name}/commits"
    params = {"since": last_year.isoformat(), "per_page": 1}
    response = requests.get(url, headers=HEADERS, params=params)

    if response.status_code == 401:
        print(f"[ERROR] Unauthorized (401) — missing or invalid GitHub token.")
        print("→ Make sure your .env file has GITHUB_TOKEN=your_token_here")
        return None

    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch commits for {repo_name}: {response.status_code}")
        return None

    commits = response.json()
    if not commits:
        print(f"[SKIP] No commits in the last year for {repo_name}")
        return None

    latest_commit = commits[0]
    lc_sha = latest_commit["sha"]
    lc_date = latest_commit["commit"]["author"]["date"]
    print(f"[INFO] Latest commit for {repo_name}: {lc_sha} ({lc_date})")
    return {"sha": lc_sha, "date": lc_date}


def clone_or_update_repo(repo_name, commit_sha):
    """Clone the repo if missing, otherwise fetch and checkout the given commit."""
    owner, name = repo_name.split("/")
    repo_dir = os.path.join(BASE_DIR, name)
    repo_url = f"https://github.com/{repo_name}.git"

    # Clone if repo doesn't exist
    if not os.path.exists(repo_dir):
        print(f"[CLONE] Cloning {repo_name}...")
        Repo.clone_from(repo_url, repo_dir)

    # Fetch and checkout
    repo = Repo(repo_dir)
    print(f"[CHECKOUT] Checking out commit {commit_sha} for {repo_name}...")
    repo.git.fetch()
    repo.git.checkout(commit_sha)


def log_skipped(repo_name, reason):
    """Log skipped repositories."""
    with open(LOG_FILE, "a") as f:
        f.write(f"{repo_name}: {reason}\n")


def save_metadata(metadata):
    """Save metadata to a JSON file."""
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=4)


# === MAIN EXECUTION ===
if __name__ == "__main__":
    # Clean previous logs
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    if os.path.exists(METADATA_FILE):
        os.remove(METADATA_FILE)

    # Load repositories
    repos = load_repos(REPOS_FILE)
    if not repos:
        print("[ERROR] No repositories to process. Exiting.")
        exit(1)

    metadata = {}

    for repo in repos:
        try:
            commit_info = get_recent_commit(repo)
            if commit_info:
                clone_or_update_repo(repo, commit_info["sha"])
                metadata[repo] = {
                    "commit_sha": commit_info["sha"],
                    "commit_date": commit_info["date"]
                }
            else:
                log_skipped(repo, "No recent commit within the last year or API error")
        except Exception as e:
            print(f"[ERROR] Exception processing {repo}: {e}")
            log_skipped(repo, str(e))

    save_metadata(metadata)
    print(f"\n[INFO] Metadata saved to {METADATA_FILE}")
