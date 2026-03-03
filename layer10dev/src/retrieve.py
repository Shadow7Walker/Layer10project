import argparse
import json
import sys
from db import MemoryGraphDB

# Force UTF-8 encoding for Windows stdout redirection
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def retrieve_context_pack(db_path: str, query: str):
    db = MemoryGraphDB(db_path)
    print(f"Searching memory graph for '{query}'...")
    
    context_pack = db.get_context_pack(query)
    
    if "error" in context_pack:
        print(f"Error: {context_pack['error']}")
        return
        
    print(f"\n--- Context Pack for '{query}' ---")
    print(f"Entity found: {context_pack['entity']['name']} (Type: {context_pack['entity']['type']})")
    print(f"Related Claims: {len(context_pack['context'])}")
    print("-" * 40)
    for item in context_pack['context']:
        print(f"\nClaim: {item['claim']} (Conf: {item['confidence']})")
        print(f"Supporting Evidence ({len(item['evidence'])} sources):")
        for ev in item['evidence']:
            print(f" - [{ev['timestamp']}] {ev['source_url']}")
            print(f"   Excerpt: \"{ev['excerpt']}\"")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the memory graph.")
    parser.add_argument("--db", type=str, default="data/memory_graph.db", help="SQLite DB path")
    parser.add_argument("--query", type=str, required=True, help="Entity to search for")
    args = parser.parse_args()
    
    retrieve_context_pack(args.db, args.query)
