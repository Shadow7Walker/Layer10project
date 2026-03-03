import streamlit as st
import sqlite3
import pandas as pd
import json
import os
from streamlit_agraph import agraph, Node, Edge, Config

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "memory_graph.db")

def get_conn():
    return sqlite3.connect(DB_PATH)

st.set_page_config(page_title="Layer10 Memory Explorer", layout="wide")
st.title("Layer10 Grounded Memory View")

st.markdown("""
This app allows you to explore the extracted entities, claims, and supporting evidence.
Data was ingested from GitHub issues and unstructured text was parsed into a structured ontology.
""")

# --- Filters Sidebar ---
st.sidebar.header("Explore Filters")
with get_conn() as conn:
    types = [row[0] for row in conn.execute("SELECT DISTINCT type FROM entities WHERE merged_into IS NULL").fetchall()]
    
type_filter = st.sidebar.multiselect("Filter by Entity Type", types, default=[])
min_conf = st.sidebar.slider("Minimum Claim Confidence", 0.0, 1.0, 0.5, 0.1)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Graph View", "Search & Retrieve", "Browse Entities", "Browse Claims", "Merge History"])

def get_filtered_entities():
    query = "SELECT id, type, name, aliases, created_at FROM entities WHERE merged_into IS NULL"
    params = []
    if type_filter:
        placeholders = ",".join("?" * len(type_filter))
        query += f" AND type IN ({placeholders})"
        params.extend(type_filter)
    with get_conn() as c:
        return pd.read_sql_query(query, c, params=params)

def get_filtered_claims():
    query = '''
        SELECT c.id, c.confidence, 
               s.name as Subject, 
               s.id as SubjectId,
               c.predicate as Predicate, 
               o.name as Object,
               o.id as ObjectId
        FROM claims c
        JOIN entities s ON c.subject_id = s.id
        JOIN entities o ON c.object_id = o.id
        WHERE c.valid_to IS NULL AND c.confidence >= ?
    '''
    params = [min_conf]
    if type_filter:
        placeholders = ",".join("?" * len(type_filter))
        query += f" AND (s.type IN ({placeholders}) OR o.type IN ({placeholders}))"
        params.extend(type_filter)
        params.extend(type_filter)

    with get_conn() as c:
        return pd.read_sql_query(query, c, params=params)


with tab1:
    st.header("Interactive Memory Graph")
    
    entities_df = get_filtered_entities()
    claims_df = get_filtered_claims()
    
    if entities_df.empty or claims_df.empty:
        st.info("Not enough data to display graph. Try broadening your filters.")
    else:
        nodes = []
        edges = []
        
        # Color palette for entity types
        colors = {"person": "#4CAF50", "issue": "#2196F3", "concept": "#FF9800", "unknown": "#9E9E9E"}
        
        # We only plot nodes that exist in our filtered entity set, or that are referenced by our filtered claims.
        active_node_ids = set(entities_df['id'].tolist()).union(set(claims_df['SubjectId'].tolist())).union(set(claims_df['ObjectId'].tolist()))
        
        # Re-fetch full name/type for these active nodes so graph isn't broken
        with get_conn() as c:
            plcs = ",".join("?" * len(active_node_ids))
            node_data = c.execute(f"SELECT id, name, type FROM entities WHERE id IN ({plcs})", list(active_node_ids)).fetchall()
        
        for n_id, name, etype in node_data:
            nodes.append(Node(
                id=n_id,
                label=name,
                size=25,
                color=colors.get(etype, colors["unknown"])
            ))
            
        for _, claim in claims_df.iterrows():
            edges.append(Edge(
                source=claim['SubjectId'],
                label=claim['Predicate'],
                target=claim['ObjectId'],
            ))
            
        config = Config(width=1000,
                        height=600,
                        directed=True,
                        physics=True,
                        hierarchical=False)

        return_value = agraph(nodes=nodes, edges=edges, config=config)

with tab2:
    st.header("Retrieve Context")
    query = st.text_input("Enter an entity or keyword (e.g., 'react', 'author_name'):")
    
    if query:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM entities WHERE (name LIKE ? OR aliases LIKE ?) AND merged_into IS NULL", 
                           (f'%{query}%', f'%{query}%'))
            entity = cursor.fetchone()
            
            if not entity:
                st.warning(f"No match found for '{query}'")
            else:
                st.success(f"Matched Entity: **{entity['name']}** (Type: {entity['type']})")
                
                cursor.execute('''
                    SELECT c.id as claim_id, s.name as subject, c.predicate, o.name as object, c.confidence
                    FROM claims c
                    JOIN entities s ON c.subject_id = s.id
                    JOIN entities o ON c.object_id = o.id
                    WHERE (c.subject_id = ? OR c.object_id = ?) AND c.valid_to IS NULL
                ''', (entity['id'], entity['id']))
                claims = cursor.fetchall()
                
                if claims:
                    st.subheader(f"Found {len(claims)} related claims:")
                    for idx, c in enumerate(claims):
                        with st.expander(f"{idx+1}. {c['subject']} -> {c['predicate']} -> {c['object']} (Conf: {c['confidence']})"):
                            
                            cursor.execute("SELECT * FROM evidence WHERE claim_id = ?", (c['claim_id'],))
                            evidence = cursor.fetchall()
                            st.markdown(f"**Supporting Evidence ({len(evidence)} sources):**")
                            for ev in evidence:
                                st.markdown(f"> *{ev['excerpt']}*")
                                st.caption(f"Source: [{ev['source_id']}]({ev['source_url']}) | Timestamp: {ev['timestamp']}")
                else:
                    st.info("No active claims found for this entity.")

with tab3:
    st.header("Entity Directory")
    st.dataframe(get_filtered_entities()[['id', 'type', 'name', 'aliases', 'created_at']], width='stretch')

with tab4:
    st.header("Claim Registry")
    st.dataframe(get_filtered_claims()[['id', 'confidence', 'Subject', 'Predicate', 'Object']], width='stretch')

with tab5:
    st.header("Merge & Deduplication History")
    st.markdown("Inspect entities that were algorithmically deduplicated and soft-deleted via canonicalization.")
    with get_conn() as conn:
        df_merges = pd.read_sql_query('''
            SELECT e1.name as "Duplicate Name", e1.type as "Type", e2.name as "Merged Into (Canonical)", e1.created_at
            FROM entities e1
            JOIN entities e2 ON e1.merged_into = e2.id
            WHERE e1.merged_into IS NOT NULL
        ''', conn)
        if df_merges.empty:
            st.info("No duplicated entities found.")
        else:
            st.dataframe(df_merges, width='stretch')
            
        st.subheader("Redundant Claims Merged")
        df_claim_merges = pd.read_sql_query('''
            SELECT c.predicate, s.name as "Subject", o.name as "Object", c.valid_to as "Invalidated At"
            FROM claims c
            JOIN entities s ON c.subject_id = s.id
            JOIN entities o ON c.object_id = o.id
            WHERE c.valid_to IS NOT NULL
        ''', conn)
        st.dataframe(df_claim_merges, width='stretch')
