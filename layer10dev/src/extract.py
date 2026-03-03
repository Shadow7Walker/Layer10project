import json
import os
import argparse
import uuid
import hashlib
import re
from typing import List, Dict, Any, Tuple
from db import MemoryGraphDB

# NOTE: For the takehome, evaluating calling a real LLM for 100s of issues is slow/costly.
# This file provides the extraction contract (schema) and a simulated/heuristic extractor 
# demonstrating the pipeline. A real production version would pass `text` to LangChain/Llama3 
# and parse the JSON output based on the Pydantic schema below.

import json
import os
import argparse
import uuid
import requests
from typing import List, Dict, Any, Tuple
from db import MemoryGraphDB

class Extractor:
    def __init__(self, db_path: str, model_name: str = "llama3"):
        self.db = MemoryGraphDB(db_path)
        self.model_name = model_name
        self.ollama_url = "http://localhost:11434/api/generate"

    def extract_from_issue(self, issue: Dict[str, Any]):
        """
        Extracts entities and claims from a single issue and its comments, 
        and inserts them directly into the memory graph.
        """
        print(f"Extracting from issue: {issue['title']}")
        
        # 1. Author Entity
        author_id = f"user_{issue['author']}"
        self.db.upsert_entity(author_id, "person", issue['author'])
        
        # 2. Issue Entity
        issue_id = issue['source_id']
        self.db.upsert_entity(issue_id, "issue", f"Issue: {issue['title']}")
        
        # Claim: Author created Issue
        claim_id_created = str(uuid.uuid5(uuid.NAMESPACE_URL, f"created_{author_id}_{issue_id}"))
        self.db.insert_claim(
            claim_id=claim_id_created,
            subject_id=author_id,
            predicate="created",
            object_id=issue_id,
        )
        # Evidence for creation
        evidence_id_created = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ev_{claim_id_created}_{issue['source_id']}"))
        self.db.insert_evidence(
            evidence_id=evidence_id_created,
            claim_id=claim_id_created,
            source_id=issue['source_id'],
            source_url=issue['url'],
            excerpt=issue['title'],
            timestamp=issue['created_at']
        )

        # 3. LLM extraction from Body
        self._extract_text(issue['body'], issue['source_id'], issue['url'], issue['created_at'], issue_id)

        # 4. Extract from Comments
        for comment in issue.get('comments', []):
            comment_author_id = f"user_{comment['author']}"
            self.db.upsert_entity(comment_author_id, "person", comment['author'])
            
            # Claim: Comment author commented on Issue
            claim_id_commented = str(uuid.uuid5(uuid.NAMESPACE_URL, f"commented_{comment_author_id}_{issue_id}_{comment['source_id']}"))
            self.db.insert_claim(
                claim_id=claim_id_commented,
                subject_id=comment_author_id,
                predicate="commented on",
                object_id=issue_id,
            )
            # Evidence
            evidence_id_commented = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ev_{claim_id_commented}_{comment['source_id']}"))
            self.db.insert_evidence(
                evidence_id=evidence_id_commented,
                claim_id=claim_id_commented,
                source_id=comment['source_id'],
                source_url=comment['url'],
                excerpt=comment['body'][:200] + "...",
                timestamp=comment['created_at']
            )
            
            # LLM extraction on comment body
            self._extract_text(comment['body'], comment['source_id'], comment['url'], comment['created_at'], issue_id)

    def _extract_text(self, text: str, source_id: str, url: str, timestamp: str, context_issue_id: str):
        """
        Uses a local Ollama LLM to perform structured extraction.
        """
        if not text or len(text) < 20: # Skip very short texts
            return
            
        prompt = f"""You are a specialized information extraction pipeline. 
Read the following text and extract facts into a structured JSON format. 

Entities can represent people, tools, frameworks, concepts, or components. 
Claims must represent a relationship between two extracted entities.
Every claim MUST have an "excerpt" containing the exact verbatim quotation from the text that proves the claim.

Return ONLY a JSON object in exactly this format, with no markdown formatting or extra text:
{{
  "entities": [
    {{"id": "entity_1", "type": "person", "name": "Alice"}},
    {{"id": "entity_2", "type": "tool", "name": "Docker"}}
  ],
  "claims": [
    {{
      "subject": "entity_1",
      "predicate": "uses",
      "object": "entity_2",
      "excerpt": "I am currently using Docker for this project."
    }}
  ]
}}

TEXT TO EXTRACT:
{text[:2000]}
"""

        try:
            # We use `requests` to call the local Ollama API
            response = requests.post(self.ollama_url, json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json" # Force JSON mode if supported
            }, timeout=30)
            
            if response.status_code != 200:
                print(f"  [LLM Error] Code {response.status_code}: {response.text}")
                return

            response_json = response.json()
            output_text = response_json.get("response", "").strip()
            
            # Parse the extracted JSON
            try:
                data = json.loads(output_text)
            except json.JSONDecodeError:
                # Sometimes models wrap JSON in markdown block even with format="json"
                if "```json" in output_text:
                    clean_text = output_text.split("```json")[1].split("```")[0].strip()
                    data = json.loads(clean_text)
                else:
                    return

            entities = data.get("entities", [])
            claims = data.get("claims", [])
            
            # Insert Entities
            for ent in entities:
                ent_id = str(ent.get("id"))
                # Make IDs globally unique per run, but deterministic based on source document and text
                deterministic_hash = hashlib.md5(f"{source_id}_{ent_id}_{ent.get('name', '')}".encode()).hexdigest()[:8]
                unique_ent_id = f"ext_{deterministic_hash}_{ent_id}" 
                ent["_uid"] = unique_ent_id # Store mapped ID back
                self.db.upsert_entity(unique_ent_id, ent.get("type", "unknown"), ent.get("name", "Unknown"))
                
                # Link newly found entity to context issue
                link_claim = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mentions_{context_issue_id}_{unique_ent_id}"))
                self.db.insert_claim(link_claim, context_issue_id, "mentions", unique_ent_id)
                self.db.insert_evidence(str(uuid.uuid5(uuid.NAMESPACE_URL, f"ev_{link_claim}_{source_id}")), link_claim, source_id, url, f"Mentioned in issue {context_issue_id}", timestamp)

            # Insert Claims
            for claim in claims:
                subject_raw = str(claim.get("subject"))
                object_raw = str(claim.get("object"))
                
                # Map back to unique IDs
                subject_id = next((e["_uid"] for e in entities if str(e.get("id")) == subject_raw), None)
                object_id = next((e["_uid"] for e in entities if str(e.get("id")) == object_raw), None)
                
                if not subject_id or not object_id:
                    continue # Skip if entity references are broken
                    
                predicate = claim.get("predicate", "related to")
                claim_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"extclaim_{source_id}_{subject_id}_{predicate}_{object_id}"))
                self.db.insert_claim(
                    claim_id=claim_id,
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id
                )
                
                # Evidence
                evidence_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"extev_{claim_id}_{source_id}"))
                self.db.insert_evidence(
                    evidence_id=evidence_id,
                    claim_id=claim_id,
                    source_id=source_id,
                    source_url=url,
                    excerpt=claim.get("excerpt", "No excerpt provided")[:500],
                    timestamp=timestamp
                )
                
        except Exception as e:
            print(f"  [LLM Warning] Extraction failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract entities and claims to DB.")
    parser.add_argument("--corpus", type=str, default="data/corpus.json", help="Input JSON corpus")
    parser.add_argument("--db", type=str, default="memory_graph.db", help="SQLite DB path")
    args = parser.parse_args()

    if not os.path.exists(args.corpus):
        print(f"Error: {args.corpus} not found.")
        exit(1)

    with open(args.corpus, "r", encoding="utf-8") as f:
        issues = json.load(f)

    extractor = Extractor(args.db)
    print(f"Loaded {len(issues)} issues. Starting extraction...")
    
    for issue in issues:
        extractor.extract_from_issue(issue)
        
    print("Done extracting into Memory Graph.")
