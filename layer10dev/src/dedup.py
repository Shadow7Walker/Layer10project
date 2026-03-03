import sqlite3
import argparse
from db import MemoryGraphDB

def run_deduplicator(db_path: str):
    """
    Finds duplicated entities (case-insensitive or alias matched) 
    and merges them using soft-merges (reversibility).
    Then deduplicates Claims.
    """
    db = MemoryGraphDB(db_path)
    print("Running Entity & Claim Deduplication...")
    
    with db._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # --- 1. Entity Canonicalization (Soft Merge) ---
        cursor.execute("SELECT lower(name) as lname, count(id) as c FROM entities WHERE merged_into IS NULL GROUP BY lower(name) HAVING c > 1")
        duplicates = [dict(row) for row in cursor.fetchall()]
        
        if not duplicates:
            print("No entity name duplicates found.")
            
        for dup in duplicates:
            lname = dup['lname']
            print(f"Merging entities similar to '{lname}'...")
            
            # Fetch all active entities with this name
            cursor.execute("SELECT id, name FROM entities WHERE lower(name) = ? AND merged_into IS NULL", (lname,))
            targets = [dict(row) for row in cursor.fetchall()]
            
            if len(targets) <= 1:
                continue
                
            canonical_target = targets[0]
            canonical_id = canonical_target['id']
            
            for t in targets[1:]:
                old_id = t['id']
                
                # Re-assign claims where this was the subject
                cursor.execute("UPDATE claims SET subject_id = ? WHERE subject_id = ?", (canonical_id, old_id))
                # Re-assign claims where this was the object
                cursor.execute("UPDATE claims SET object_id = ? WHERE object_id = ?", (canonical_id, old_id))
                
                # Soft delete old duplicate entity by setting merged_into
                cursor.execute("UPDATE entities SET merged_into = ? WHERE id = ?", (canonical_id, old_id))
                
            conn.commit()
            print(f" -> Merged {len(targets)-1} duplicate(s) into {canonical_id}")
            
        # --- 2. Claim Deduplication ---
        print("\nRunning Claim Deduplication...")
        # Find claims with same Subject, Predicate, Object
        cursor.execute('''
            SELECT subject_id, predicate, object_id, count(id) as c 
            FROM claims 
            WHERE valid_to IS NULL 
            GROUP BY subject_id, predicate, object_id 
            HAVING c > 1
        ''')
        duplicate_claims_groups = [dict(row) for row in cursor.fetchall()]

        for group in duplicate_claims_groups:
            # Get all claims in this exact relation group
            cursor.execute('''
                SELECT id FROM claims 
                WHERE subject_id = ? AND predicate = ? AND object_id = ? AND valid_to IS NULL
            ''', (group['subject_id'], group['predicate'], group['object_id']))
            claims_in_group = [row['id'] for row in cursor.fetchall()]
            
            if len(claims_in_group) <= 1:
                continue

            canonical_claim_id = claims_in_group[0]
            redundant_claim_ids = claims_in_group[1:]

            # Move all evidence to the canonical claim
            for r_id in redundant_claim_ids:
                cursor.execute("UPDATE evidence SET claim_id = ? WHERE claim_id = ?", (canonical_claim_id, r_id))
                
                # Mark redundant claims as invalid (soft delete)
                cursor.execute("UPDATE claims SET valid_to = CURRENT_TIMESTAMP WHERE id = ?", (r_id,))
            
            conn.commit()
            print(f" -> Merged {len(redundant_claim_ids)} duplicate claim(s) into {canonical_claim_id}")

    print("Deduplication complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deduplicate memory graph.")
    parser.add_argument("--db", type=str, default="data/memory_graph.db", help="SQLite DB path")
    args = parser.parse_args()
    
    run_deduplicator(args.db)
