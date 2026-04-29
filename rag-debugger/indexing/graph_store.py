import os
import networkx as nx
from typing import Dict, Any, List

GRAPH_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dependency_graph.graphml")

def load_graph() -> nx.DiGraph:
    """Loads the dependency graph from disk or returns a new one."""
    if os.path.exists(GRAPH_PATH):
        try:
            return nx.read_graphml(GRAPH_PATH)
        except Exception as e:
            print(f"Error loading graph, returning new: {e}")
    return nx.DiGraph()

def save_graph(graph: nx.DiGraph):
    """Saves the dependency graph to disk."""
    os.makedirs(os.path.dirname(GRAPH_PATH), exist_ok=True)
    nx.write_graphml(graph, GRAPH_PATH)

def clear_graph():
    """Removes the persistent graph store."""
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)

def build_graph_from_chunks(chunks: List[Dict[str, Any]], existing_graph: nx.DiGraph = None) -> nx.DiGraph:
    """
    Given a list of structured entities (chunks), builds or updates a directed graph.
    """
    G = existing_graph if existing_graph is not None else nx.DiGraph()
    
    node_id_map = {}
    
    # First pass: Add/Update nodes
    for chunk in chunks:
        node_id = f"{chunk['repo']}/{chunk['file']}/{chunk['name']}"
        G.add_node(
            node_id, 
            type=chunk.get('entity_type', 'unknown'),
            repo=chunk.get('repo', ''),
            file=chunk.get('file', ''),
            name=chunk.get('name', ''),
            tokens=chunk.get('tokens', 0)
        )
        chunk['node_id'] = node_id
        node_id_map[chunk['name']] = node_id

    # Second pass: Build Relationships (Edges)
    for chunk in chunks:
        node_id = chunk['node_id']
        
        # Link function calls
        for call in chunk.get('calls', []):
            # Simple resolution: search if any node matches this name within the known mapping
            # For a production system, this would involve precise static analysis and scope resolution.
            target_node_id = None
            
            # 1. Try exact match in the same repo mapping (simplified)
            if call in node_id_map:
                target_node_id = node_id_map[call]
            
            # 2. Try graph global search for cross-repo / internal calls that are previously indexed
            if not target_node_id:
                for n, data in G.nodes(data=True):
                    if data.get('name') == call or str(data.get('name')).endswith(f".{call}"):
                        target_node_id = n
                        break
            
            if target_node_id:
                G.add_edge(node_id, target_node_id, relationship="CALLS")
                # Mutate chunk for debugging later
                chunk.setdefault('external_calls', []).append({"repo": G.nodes[target_node_id].get('repo'), "function": call})
                
        # Link to parent scopes (methods -> class)
        if "." in chunk['name']:
            parent_name = chunk['name'].rsplit(".", 1)[0]
            parent_id = f"{chunk['repo']}/{chunk['file']}/{parent_name}"
            if G.has_node(parent_id):
                G.add_edge(node_id, parent_id, relationship="BELONGS_TO")

    return G
