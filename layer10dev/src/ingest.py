import requests
import json
import os
import argparse
from typing import List, Dict, Any

def fetch_github_issues(owner: str, repo: str, num_issues: int = 10, token: str = None) -> List[Dict[str, Any]]:
    """Fetches closed issues from a public GitHub repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
        
    params = {
        "state": "closed",
        "per_page": min(100, num_issues),
        "sort": "updated",
        "direction": "desc"
    }

    issues_data = []
    print(f"Fetching issues from {owner}/{repo}...")
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Error fetching issues: {response.status_code} - {response.text}")
        return []
        
    for item in response.json():
        if "pull_request" not in item: # Filter out PRs, keep only standard issues
            
            # Fetch comments for this issue
            comments_url = item["comments_url"]
            comments_resp = requests.get(comments_url, headers=headers)
            comments = comments_resp.json() if comments_resp.status_code == 200 else []
            
            issue_record = {
                "source_id": f"github_issue_{item['number']}",
                "url": item["html_url"],
                "author": item["user"]["login"],
                "title": item["title"],
                "body": item["body"] or "",
                "created_at": item["created_at"],
                "closed_at": item["closed_at"],
                "comments": [
                    {
                        "source_id": f"github_comment_{c['id']}",
                        "url": c["html_url"],
                        "author": c["user"]["login"],
                        "body": c["body"],
                        "created_at": c["created_at"]
                    } for c in comments
                ]
            }
            issues_data.append(issue_record)
            if len(issues_data) >= num_issues:
                break
                
    return issues_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest GitHub Issues as a corpus.")
    parser.add_argument("--owner", type=str, default="fastapi", help="GitHub Repo Owner")
    parser.add_argument("--repo", type=str, default="fastapi", help="GitHub Repo Name")
    parser.add_argument("--count", type=int, default=10, help="Number of issues to fetch")
    parser.add_argument("--output", type=str, default="data/corpus.json", help="Output JSON path")
    args = parser.parse_args()

    # Create data dir if not exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    data = fetch_github_issues(args.owner, args.repo, args.count)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    print(f"Saved {len(data)} issues to {args.output}")
