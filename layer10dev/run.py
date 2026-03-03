import argparse
import subprocess
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Layer10 Take-Home: Unified Pipeline Runner")
    parser.add_argument("--owner", type=str, required=True, help="GitHub Repository Owner (e.g., 'facebook')")
    parser.add_argument("--repo", type=str, required=True, help="GitHub Repository Name (e.g., 'react')")
    parser.add_argument("--count", type=int, default=10, help="Number of issues to fetch (default: 10)")
    parser.add_argument("--query", type=str, default="", help="Optional test query to run after deduplication (e.g., 'bug')")
    
    args = parser.parse_args()

    # Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(base_dir, "src")
    data_dir = os.path.join(base_dir, "data")
    
    corpus_path = os.path.join(data_dir, "corpus.json")
    db_path = os.path.join(data_dir, "memory_graph.db")

    print("\n" + "="*50)
    print(f" Layer10 Pipeline: {args.owner}/{args.repo} ")
    print("="*50 + "\n")

    # Base commands
    py_cmd = ["uv", "run", "python"]

    # Step 1: Ingest
    print(f"[1/4] Ingesting {args.count} issues...")
    subprocess.run([*py_cmd, os.path.join(src_dir, "ingest.py"), 
                    "--owner", args.owner, "--repo", args.repo, "--count", str(args.count), "--output", corpus_path], check=True)

    # Step 2: Extract
    print("\n[2/4] Running Structured Extraction (Memory Graph)...")
    subprocess.run([*py_cmd, os.path.join(src_dir, "extract.py"), 
                    "--corpus", corpus_path, "--db", db_path], check=True)

    # Step 3: Deduplicate
    print("\n[3/4] Deduping and Canonicalizing Entities...")
    subprocess.run([*py_cmd, os.path.join(src_dir, "dedup.py"), 
                    "--db", db_path], check=True)

    # Step 4: Optional Query Test
    if args.query:
        print(f"\n[4/4] Retrieving Context Pack for '{args.query}'...")
        subprocess.run([*py_cmd, os.path.join(src_dir, "retrieve.py"), 
                        "--db", db_path, "--query", args.query])
    else:
        print("\n[4/4] Skipping retrieval test (no --query provided).")

    print("\n" + "="*50)
    print(" Pipeline Complete! ")
    print(" You can now run:  uv run streamlit run src/app.py")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
