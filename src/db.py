import sqlite3
import json
import os
from typing import Dict, Any, List, Optional

class MemoryGraphDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Entities Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    aliases TEXT DEFAULT '[]',
                    merged_into TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (merged_into) REFERENCES entities(id)
                )
            ''')
            
            # Claims Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    valid_to TIMESTAMP DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (subject_id) REFERENCES entities(id),
                    FOREIGN KEY (object_id) REFERENCES entities(id)
                )
            ''')
            
            # Evidence Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    acl_grants TEXT DEFAULT '["public"]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (claim_id) REFERENCES claims(id)
                )
            ''')
            
            # Create Indices for frequent queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_claims_object ON claims(object_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id)')
            
            conn.commit()

    def upsert_entity(self, entity_id: str, etype: str, name: str, aliases: List[str] = None):
        """Insert or update an entity."""
        if aliases is None:
            aliases = []
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO entities (id, type, name, aliases) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET 
                    type=excluded.type,
                    name=excluded.name,
                    aliases=json_insert(aliases, '$[#]', excluded.aliases) -- Note: in a real implementation we'd merge JSON arrays properly
                ''',
                (entity_id, etype, name, json.dumps(aliases))
            )
            conn.commit()

    def insert_claim(self, claim_id: str, subject_id: str, predicate: str, object_id: str, confidence: float = 1.0):
        """Insert a claim."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR IGNORE INTO claims (id, subject_id, predicate, object_id, confidence)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (claim_id, subject_id, predicate, object_id, confidence)
            )
            conn.commit()

    def insert_evidence(self, evidence_id: str, claim_id: str, source_id: str, source_url: str, excerpt: str, timestamp: str):
        """Insert evidence backing a claim."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR IGNORE INTO evidence (id, claim_id, source_id, source_url, excerpt, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (evidence_id, claim_id, source_id, source_url, excerpt, timestamp)
            )
            conn.commit()
            
    def get_context_pack(self, query: str) -> Dict[str, Any]:
        """Retrieve an entity and its active claims to form a context pack."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Find Active Entity (not merged away)
            cursor.execute(
                "SELECT * FROM entities WHERE (name LIKE ? OR aliases LIKE ?) AND merged_into IS NULL LIMIT 1",
                (f'%{query}%', f'%{query}%')
            )
            entity_row = cursor.fetchone()
            
            if not entity_row:
                return {"error": f"No active entity found matching '{query}'"}
            
            entity = dict(entity_row)
            entity['aliases'] = json.loads(entity['aliases'])
            
            # Find Active Claims related to this entity
            cursor.execute(
                '''
                SELECT c.id as claim_id, s.name as subject, c.predicate, o.name as object, c.confidence
                FROM claims c
                JOIN entities s ON c.subject_id = s.id
                JOIN entities o ON c.object_id = o.id
                WHERE (c.subject_id = ? OR c.object_id = ?)
                AND c.valid_to IS NULL
                ''', 
                (entity['id'], entity['id'])
            )
            claim_rows = cursor.fetchall()
            
            context = []
            for c_row in claim_rows:
                claim_id = c_row['claim_id']
                claim_str = f"{c_row['subject']} -> {c_row['predicate']} -> {c_row['object']}"
                
                # Fetch evidence for this claim
                cursor.execute("SELECT source_url, excerpt, timestamp FROM evidence WHERE claim_id = ?", (claim_id,))
                evidence_rows = [dict(e) for e in cursor.fetchall()]
                
                context.append({
                    "claim_id": claim_id,
                    "claim": claim_str,
                    "confidence": c_row['confidence'],
                    "evidence": evidence_rows
                })
                
            return {
                "entity": entity,
                "context": context
            }
