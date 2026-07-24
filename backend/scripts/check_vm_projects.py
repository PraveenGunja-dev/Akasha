"""
VM Project Status Checker
=========================
Scans the D:\ drive for all git repositories and reports:
  - Current branch
  - Remote URL
  - Uncommitted / unstaged changes
  - Unpushed commits
  - Untracked files

Usage:
    python check_vm_projects.py
    python check_vm_projects.py --path E:\  (scan a different drive)
    python check_vm_projects.py --depth 3   (search deeper)
"""

import os
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_git(repo_path: str, *args: str) -> str:
    """Run a git command in the given repo and return stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_repo_info(repo_path: str) -> dict:
    """Gather status information for a single git repository."""
    branch = run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    remote = run_git(repo_path, "remote", "get-url", "origin") or "no remote"

    # Staged changes
    staged = run_git(repo_path, "diff", "--cached", "--name-only")
    staged_files = [f for f in staged.splitlines() if f]

    # Unstaged changes
    unstaged = run_git(repo_path, "diff", "--name-only")
    unstaged_files = [f for f in unstaged.splitlines() if f]

    # Untracked files
    untracked = run_git(repo_path, "ls-files", "--others", "--exclude-standard")
    untracked_files = [f for f in untracked.splitlines() if f]

    # Unpushed commits
    unpushed_raw = run_git(repo_path, "log", "--oneline", f"origin/{branch}..HEAD")
    unpushed = [l for l in unpushed_raw.splitlines() if l] if unpushed_raw else []

    # Last commit info
    last_commit = run_git(repo_path, "log", "-1", "--format=%h %s (%cr)")

    return {
        "path": repo_path,
        "branch": branch,
        "remote": remote,
        "staged": staged_files,
        "unstaged": unstaged_files,
        "untracked": untracked_files,
        "unpushed": unpushed,
        "last_commit": last_commit,
    }


def find_git_repos(root: str, max_depth: int = 2) -> list[str]:
    """Walk directories up to max_depth and return paths containing .git."""
    repos = []
    root = os.path.abspath(root)

    for dirpath, dirnames, _ in os.walk(root):
        # Calculate current depth
        depth = dirpath.replace(root, "").count(os.sep)
        if depth >= max_depth:
            dirnames.clear()
            continue

        # Skip common non-project dirs
        dirnames[:] = [
            d for d in dirnames
            if d not in {
                "node_modules", ".pnpm-store", "__pycache__", ".venv",
                "venv", "env", "$RECYCLE.BIN", "System Volume Information",
                "hf-cache", "msdownld.tmp", ".git",
            }
        ]

        if ".git" in os.listdir(dirpath):
            repos.append(dirpath)

    return sorted(repos)


# ── Display ──────────────────────────────────────────────────────────────────

STATUS_ICONS = {
    "clean": "✅",
    "dirty": "⚠️",
    "unpushed": "⬆️",
    "error": "❌",
}


def print_report(repos_info: list[dict]):
    """Print a formatted report of all repositories."""
    width = 80
    print("\n" + "=" * width)
    print(f"  🖥️  VM PROJECT STATUS REPORT")
    print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📁 {len(repos_info)} repositories found")
    print("=" * width)

    clean_count = 0
    dirty_count = 0
    unpushed_count = 0

    for info in repos_info:
        has_changes = info["staged"] or info["unstaged"] or info["untracked"]
        has_unpushed = bool(info["unpushed"])

        if has_changes:
            dirty_count += 1
        else:
            clean_count += 1
        if has_unpushed:
            unpushed_count += 1

        # Status icon
        if has_changes and has_unpushed:
            icon = f"{STATUS_ICONS['dirty']} {STATUS_ICONS['unpushed']}"
        elif has_changes:
            icon = STATUS_ICONS["dirty"]
        elif has_unpushed:
            icon = STATUS_ICONS["unpushed"]
        else:
            icon = STATUS_ICONS["clean"]

        print(f"\n{'─' * width}")
        print(f"  {icon}  {info['path']}")
        print(f"      Branch: {info['branch']}  |  Remote: {info['remote']}")

        if info["last_commit"]:
            print(f"      Last commit: {info['last_commit']}")

        if info["staged"]:
            print(f"      📝 Staged ({len(info['staged'])}):")
            for f in info["staged"][:10]:
                print(f"           + {f}")
            if len(info["staged"]) > 10:
                print(f"           ... and {len(info['staged']) - 10} more")

        if info["unstaged"]:
            print(f"      🔴 Unstaged ({len(info['unstaged'])}):")
            for f in info["unstaged"][:10]:
                print(f"           ~ {f}")
            if len(info["unstaged"]) > 10:
                print(f"           ... and {len(info['unstaged']) - 10} more")

        if info["untracked"]:
            print(f"      ❓ Untracked ({len(info['untracked'])}):")
            for f in info["untracked"][:10]:
                print(f"           ? {f}")
            if len(info["untracked"]) > 10:
                print(f"           ... and {len(info['untracked']) - 10} more")

        if info["unpushed"]:
            print(f"      ⬆️  Unpushed commits ({len(info['unpushed'])}):")
            for c in info["unpushed"][:5]:
                print(f"           → {c}")
            if len(info["unpushed"]) > 5:
                print(f"           ... and {len(info['unpushed']) - 5} more")

        if not has_changes and not has_unpushed:
            print("      All clean — nothing to commit or push.")

    # Summary
    print(f"\n{'=' * width}")
    print(f"  📊 SUMMARY")
    print(f"      {STATUS_ICONS['clean']} Clean:    {clean_count}")
    print(f"      {STATUS_ICONS['dirty']} Dirty:    {dirty_count}")
    print(f"      {STATUS_ICONS['unpushed']} Unpushed: {unpushed_count}")
    print("=" * width + "\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Check git status of all projects on the VM")
    parser.add_argument("--path", default="D:\\", help="Root path to scan (default: D:\\)")
    parser.add_argument("--depth", type=int, default=3, help="Max directory depth to search (default: 3)")
    args = parser.parse_args()

    print(f"\n🔍 Scanning '{args.path}' for git repositories (depth={args.depth})...")
    repos = find_git_repos(args.path, max_depth=args.depth)

    if not repos:
        print("❌ No git repositories found.")
        return

    print(f"   Found {len(repos)} repositories. Gathering status...\n")

    repos_info = []
    for repo in repos:
        try:
            info = get_repo_info(repo)
            repos_info.append(info)
        except Exception as e:
            repos_info.append({
                "path": repo,
                "branch": "error",
                "remote": str(e),
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "unpushed": [],
                "last_commit": "",
            })

    print_report(repos_info)


if __name__ == "__main__":
    main()
