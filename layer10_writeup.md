# Layer10 Take-Home Project 2026: Grounded Memory Graph

## 1. Corpus
I chose the public **GitHub Issues** corpus, specifically downloading issues from popular open source repositories (defaulting to `facebook/react`). GitHub issues map perfectly to Layer10’s focus on unstructured communication and structured work artifacts, providing rich identity-resolution challenges (usernames vs emails vs real names) and historical context (comments spanning years). 

## 2. Ontology & Extraction Contract
- **Entity**: Broadly represents a person, project, framework, concept, or component. Has an `id`, `type`, `name`, and `aliases` (JSON array).
- **Claim**: A typed relation between a `subject` (Entity) and `object` (Entity), with an optional validity window (to represent facts that change over time).
- **Evidence**: Directly links a Claim back to the exact source artifact (`source_id`), url, and text snippet.

Extraction Contract:
We use **Ollama** running locally (e.g., `llama3`) to fulfill the "use a free model" requirement without API costs. An LLM is passed an issue body or comment along with its timestamp and URL. The prompt asks the model to emit a JSON list of Entities and Claims based on the text. Every Claim must be accompanied by the exact unbroken string from the original text that justifies it, which is saved to the Evidence table.
## 3. Deduplication and Canonicalization
- **Artifact dedup**: During ingestion, GitHub natively guarantees unique `issue_id`s and `comment_id`s. If syncing email, we would rely on `Message-ID`.
- **Entity canonicalization**: We run an offline job (`dedup.py`) that searches for likely aliases (e.g. by case-insensitive name, or in reality, cosine similarity of embeddings). It merges the objects, updates all associated Claims to point to the canonical ID, and adds the merged names to the `aliases` column. Soft deletes or tombstoning could make this reversible.
- **Claim dedup**: If multiple people report that "React 19 supports X", they are mapped to the exact same `Claim` row. Instead of duplicating the claim, we insert multiple `Evidence` rows attached to that claim, demonstrating that the fact is mutually supported across multiple points in time.

## 4. Updates & Revisions
- **Updates**: Incremental ingestion is supported. If a system fetches a new comment, the claims are appended. If an issue is edited, the ingestion pipeline can `UPSERT` the updated text and soft-delete claims that were invalidated by the edit.
- **Temporal Validity**: If an architectural decision is reversed, the existing Claim is annotated with a `valid_to` timestamp, and a new Claim is inserted. The UI then highlights only "current" claims by default.

## 5. Layer10 Adaptations
To adapt this for an enterprise application (Email, Slack, Jira):
1. **Unstructured + Structured Fusion**: Since Slack discussions often correlate to Jira tickets, we need cross-system heuristics. When Slack messages drop a link like "jira.com/L10-45", we explicitly extract a claim `Message -> References -> Ticket`.
2. **Permissions (Crucial)**: In the DB, the `Evidence` table must inherit the ACLs (Access Control Lists) of the source system. When a user runs `retrieve.py`, we must inject a filter `WHERE evidence.acl_grants IN (user_acls)` before aggregating the claims. This guarantees a user only sees memories grounded in documents they already have permission to access.
3. **Operational Reality**: For scale, SQLite cannot absorb the write throughput of Slack. We would migrate to Postgres. For extraction, relying purely on LLMs is expensive; we would train cheaper small models (e.g., fine-tuned Llama-3 8B) specifically for token classification and relationship extraction to drastically reduce cost.

## 6. How to Run

1. **Start Ollama** (Required for the extraction LLM step):
    ```bash
    ollama run llama3
    ```
2. **Execute the ingestion and extraction pipeline**:
    ```bash
    uv run python run.py --owner facebook --repo react --count 5
    ```

## 7. Output Deliverables
The requirements requested serialized output from the memory graph and retrieval packages.
- The compiled graph exists locally as `data/memory_graph.db`.
- Example retrieval context packs have been generated into `output_react_context_pack.txt` and `output_bug_context_pack.txt`.
