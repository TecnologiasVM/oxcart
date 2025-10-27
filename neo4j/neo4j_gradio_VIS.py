import os
import gradio as gr
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError
from neo4j.graph import Node, Relationship, Path
from typing import Optional
import base64
import json

# ======== Config interna (oculta al usuario) ========
URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "xyz12345")
CANVAS_HEIGHT = 700  # px
DBNAME = os.getenv("NEO4J_DATABASE", "neo4j")

PALETTE = {
    "Stamp": "#4e79a7",
    "Issue": "#f28e2b",
    "Person": "#59a14f",
    "Printer": "#e15759",
    "LegalAct": "#76b7b2",
    "Variety": "#edc948",
    "Specimen": "#b07aa1",
    "Plate": "#ff9da7",
    "PlatePosition": "#9c755f",
    "Proof": "#bab0ac",
    "DieProof": "#d4a6c8",
    "PlateProof": "#fabfd2",
    "ColorProof": "#d7b5a6",
    "ProductionOrder": "#79706e",
    "Quantity": "#bcbd22",
    "RemaindersEvent": "#17becf",
    "Essay": "#8c564b"
}

DEFAULT_CYPHER = """
WITH 'correos' AS q   // ej. 'first issue', 'surcharges', '1881-82'

MATCH (iss:Issue)
WHERE toLower(iss.title)    CONTAINS toLower(q)
   OR toLower(iss.issue_id) CONTAINS toLower(q)

// 1 salto: Issue -> Stamp (siempre)
MATCH p1 = (iss)-[:HAS_STAMP]->(s:Stamp)

// 2° salto opcional: Stamp -> Variety (si existe)
OPTIONAL MATCH p2 = (s)-[:HAS_VARIETY]->(v:Variety)

RETURN p1, p2
LIMIT 5000;
""".strip()

def run_cypher(cypher_text: str):
    """Execute Cypher and return animated HTML graph with vis.js"""
    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    except AuthError as e:
        return f"<pre>❌ AuthError: {e}</pre>"

    nodes_map = {}  # element_id -> dict (avoid duplicates)
    rels_map = {}   # element_id -> dict (avoid duplicates) - CAMBIADO de lista a diccionario

    try:
        session_kwargs = {}
        if DBNAME:
            session_kwargs["database"] = DBNAME

        with driver.session(**session_kwargs) as session:
            result = session.run(cypher_text)

            for record in result:
                for val in record.values():
                    if isinstance(val, Node):
                        _add_node(val, nodes_map)
                    elif isinstance(val, Relationship):
                        _add_rel(val, rels_map)
                        _add_node(val.start_node, nodes_map)
                        _add_node(val.end_node, nodes_map)
                    elif isinstance(val, Path):
                        for n in val.nodes:
                            _add_node(n, nodes_map)
                        for r in val.relationships:
                            _add_rel(r, rels_map)
                    elif isinstance(val, list) or isinstance(val, tuple):
                        for x in val:
                            if isinstance(x, Node):
                                _add_node(x, nodes_map)
                            elif isinstance(x, Relationship):
                                _add_rel(x, rels_map)
                                _add_node(x.start_node, nodes_map)
                                _add_node(x.end_node, nodes_map)
                            elif isinstance(x, Path):
                                for n in x.nodes:
                                    _add_node(n, nodes_map)
                                for r in x.relationships:
                                    _add_rel(r, rels_map)

    except AuthError as e:
        return f"<pre>❌ AuthError: {e}</pre>"
    except Exception as e:
        return f"<pre>❌ Error running Cypher: {e}</pre>"
    finally:
        driver.close()

    if not nodes_map and not rels_map:
        return (
            "<div style=\"padding:1rem;border-radius:8px;background:#111;color:#eee;\">"
            "No nodes or relationships were returned. Try a different Cypher query."
            "</div>"
        )

    # Build visualization HTML
    html = _generate_vis_html(nodes_map, rels_map)
    
    # Wrap inside iframe
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    iframe = (
        f'<iframe style="width:100%;height:{CANVAS_HEIGHT}px;border:0;border-radius:10px;" '
        f'sandbox="allow-scripts allow-same-origin allow-fullscreen" '
        f'allowfullscreen '
        f'src="data:text/html;charset=utf-8;base64,{b64}"></iframe>'
    )
    return iframe

def _serialize_value(val):
    """Convert Neo4j types to JSON-serializable values"""
    if val is None:
        return None
    if hasattr(val, 'iso_format'):
        return val.iso_format()
    if hasattr(val, 'x') and hasattr(val, 'y'):
        return f"Point({val.x}, {val.y})"
    if hasattr(val, 'months') and hasattr(val, 'days'):
        return str(val)
    if hasattr(val, '__dict__') and not isinstance(val, (str, int, float, bool, list, dict)):
        return str(val)
    return val

def _serialize_properties(props: dict) -> dict:
    """Convert all properties to JSON-serializable format"""
    serialized = {}
    for key, val in props.items():
        try:
            if isinstance(val, list):
                serialized[key] = [_serialize_value(v) for v in val]
            else:
                serialized[key] = _serialize_value(val)
        except Exception:
            serialized[key] = str(val)
    return serialized

def _generate_vis_html(nodes_map: dict, rels_map: dict) -> str:
    """Generate HTML using vis.js with modern styling"""
    
    # Calculate degree for node sizing
    degree = {k: 0 for k in nodes_map.keys()}
    for e in rels_map.values():  # Iterar sobre values() del diccionario
        if e["from"] in degree: 
            degree[e["from"]] += 1
        if e["to"] in degree: 
            degree[e["to"]] += 1
    
    # Prepare nodes data
    vis_nodes = []
    for nid, node in nodes_map.items():
        node_degree = degree.get(nid, 1)
        size = 30 + (node_degree * 3)
        
        props = node.get("_props", {}) or {}
        # Exclude any property keys that mention 'embedding' or 'search_corpus' (case-insensitive)
        filtered_props = {
            k: v for k, v in props.items()
            if not any(sub in k.lower() for sub in ('embedding', 'search_corpus'))
        }
        serialized_props = _serialize_properties(filtered_props)
        
        vis_nodes.append({
            "id": nid,
            "label": node["caption"],
            "labelFull": node.get("caption_full", node["caption"]),
            "color": node["color"],
            "size": size,
            "font": {
                "color": "#ffffff",
                "size": 13,
                "face": "Inter, sans-serif",
                "bold": "600"
            },
            "group": node["group"],
            "title": _create_tooltip(node),
            "properties": serialized_props
        })
    
    # Prepare edges data - convertir diccionario a lista
    vis_edges = []
    for rel in rels_map.values():  # Usar .values() para obtener solo los valores
        rel_props = rel.get("properties", {})
        
        vis_edges.append({
            "from": rel["from"],
            "to": rel["to"],
            "label": rel["label"],
            "arrows": "to",
            "title": rel.get("title", ""),
            "color": {
                "color": "rgba(150, 166, 186, 0.5)",
                "highlight": "rgba(156, 192, 255, 0.8)"
            },
            "width": 2,
            "font": {
                "size": 11,
                "color": "#97a6ba",
                "background": "rgba(12, 17, 23, 0.85)",
                "strokeWidth": 0
            },
            "properties": rel_props
        })
    
    nodes_json = json.dumps(vis_nodes, indent=2)
    edges_json = json.dumps(vis_edges, indent=2)
    palette_json = json.dumps(PALETTE)
    
    # Get used groups for legend
    used_groups = sorted(list(set(n["group"] for n in nodes_map.values() if n["group"])))
    legend_items = "".join(
        f'<div class="legend-item"><span class="legend-color" style="background:{PALETTE.get(g, "#8892a6")}"></span>{g}</div>'
        for g in used_groups
    )
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Neo4j Graph Visualization</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0e14;
            color: #e6eef8;
            overflow: hidden;
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100vh;
        }}
        
        body.expanded {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 9999;
        }}
        
        #network {{
            width: 100%;
            height: 100vh;
            background: #0a0e14;
        }}
        
        #legend {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(12, 17, 23, 0.95);
            backdrop-filter: blur(10px);
            border: 1px solid #2b3240;
            border-radius: 12px;
            padding: 16px;
            max-width: 260px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            z-index: 1000;
        }}
        
        #legend h3 {{
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 12px;
            color: #9cc0ff;
            letter-spacing: 0.3px;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 8px 0;
            font-size: 13px;
            color: #e6eef8;
        }}
        
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid rgba(255, 255, 255, 0.1);
            flex-shrink: 0;
        }}
        
        #controls {{
            position: fixed;
            bottom: 20px;
            left: 20px;
            display: flex;
            gap: 10px;
            z-index: 1000;
        }}
        
        .control-btn {{
            background: rgba(22, 32, 51, 0.95);
            backdrop-filter: blur(10px);
            color: #e6eef8;
            border: 1px solid #2b3240;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
        }}
        
        .control-btn:hover {{
            background: rgba(27, 39, 64, 0.95);
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }}
        
        .control-btn:active {{
            transform: translateY(0);
        }}
        
        #info {{
            position: fixed;
            bottom: 80px;
            left: 20px;
            background: rgba(12, 17, 23, 0.95);
            backdrop-filter: blur(10px);
            border: 1px solid #2b3240;
            border-radius: 12px;
            padding: 16px;
            max-width: 380px;
            max-height: 400px;
            overflow-y: auto;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            z-index: 1000;
            display: none;
        }}
        
        #info.active {{
            display: block;
        }}
        
        #info h3 {{
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 10px;
            color: #9cc0ff;
        }}
        
        #info table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }}
        
        #info th {{
            text-align: left;
            padding: 6px 8px;
            color: #97a6ba;
            font-weight: 600;
            border-bottom: 1px solid #1f2632;
        }}
        
        #info td {{
            padding: 6px 8px;
            color: #e6eef8;
            border-bottom: 1px solid #1f2632;
            word-break: break-word;
        }}
        
        #info tr:last-child td {{
            border-bottom: none;
        }}
        
        .stats {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(12, 17, 23, 0.95);
            backdrop-filter: blur(10px);
            border: 1px solid #2b3240;
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 12px;
            color: #97a6ba;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            z-index: 1000;
        }}
        
        .stats span {{
            color: #9cc0ff;
            font-weight: 700;
        }}

        .vis-tooltip {{
            background: rgba(16, 21, 27, 0.98) !important;
            border: 1px solid #2b3240 !important;
            border-radius: 8px !important;
            color: #e6eef8 !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 12px !important;
            padding: 10px 12px !important;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35) !important;
            max-width: 400px !important;
        }}
    </style>
</head>
<body>
    <div id="network"></div>
    
    <div class="stats">
        Nodes: <span id="nodeCount">{len(nodes_map)}</span> | Relationships: <span id="relCount">{len(rels_map)}</span>
    </div>
    
    <div id="legend">
        <h3>Node Types</h3>
        {legend_items}
    </div>
    
    <div id="controls">
        <button class="control-btn" onclick="resetView()">🔄 Reset View</button>
        <button class="control-btn" id="physicsBtn" onclick="togglePhysics()">⏸ Pause Physics</button>
        <button class="control-btn" id="fullscreenBtn" onclick="toggleFullscreen()">⛶ Fullscreen</button>
    </div>
    
    <div id="info">
        <h3 id="infoTitle">Node Details</h3>
        <table id="infoTable"></table>
    </div>

    <script>
        const nodes = new vis.DataSet({nodes_json});
        const edges = new vis.DataSet({edges_json});
        
        const container = document.getElementById('network');
        const data = {{ nodes: nodes, edges: edges }};
        
        const options = {{
            nodes: {{
                shape: 'dot',
                borderWidth: 2,
                borderWidthSelected: 3,
                shadow: {{
                    enabled: true,
                    color: 'rgba(0,0,0,0.3)',
                    size: 8,
                    x: 0,
                    y: 2
                }},
                font: {{
                    color: '#ffffff',
                    size: 13,
                    face: 'Inter, sans-serif',
                    bold: '600'
                }}
            }},
            edges: {{
                width: 2,
                color: {{
                    color: 'rgba(150, 166, 186, 0.5)',
                    highlight: 'rgba(156, 192, 255, 0.8)',
                    hover: 'rgba(156, 192, 255, 0.6)'
                }},
                arrows: {{
                    to: {{
                        enabled: true,
                        scaleFactor: 0.8
                    }}
                }},
                smooth: {{
                    type: 'dynamic',
                    roundness: 0.5
                }},
                font: {{
                    size: 11,
                    color: '#97a6ba',
                    background: 'rgba(12, 17, 23, 0.85)',
                    strokeWidth: 0,
                    align: 'horizontal'
                }}
            }},
            physics: {{
                enabled: true,
                stabilization: {{
                    enabled: true,
                    iterations: 250,
                    updateInterval: 25,
                    fit: true
                }},
                barnesHut: {{
                    gravitationalConstant: -10000,
                    centralGravity: 0.3,
                    springLength: 180,
                    springConstant: 0.04,
                    damping: 0.5,
                    avoidOverlap: 0.3
                }},
                minVelocity: 0.75,
                maxVelocity: 50
            }},
            interaction: {{
                hover: true,
                navigationButtons: false,
                keyboard: true,
                tooltipDelay: 100,
                hideEdgesOnDrag: false,
                hideEdgesOnZoom: false
            }}
        }};
        
        const network = new vis.Network(container, data, options);
        
        let physicsEnabled = true;
        let selectedNodeId = null;
        
        // Auto-stop physics after stabilization
        network.once('stabilizationIterationsDone', function() {{
            setTimeout(() => {{
                network.setOptions({{ physics: false }});
                physicsEnabled = false;
                document.getElementById('physicsBtn').textContent = '▶ Play Physics';
            }}, 15000);
        }});
        
        // Handle node clicks
        network.on('click', function(params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodes.get(nodeId);
                
                // Restore previous node label
                if (selectedNodeId && selectedNodeId !== nodeId) {{
                    const prevNode = nodes.get(selectedNodeId);
                    if (prevNode && prevNode.labelFull) {{
                        const shortLabel = prevNode.labelFull.length > 30 
                            ? prevNode.labelFull.substring(0, 28) + '…' 
                            : prevNode.labelFull;
                        nodes.update({{id: selectedNodeId, label: shortLabel}});
                    }}
                }}
                
                // Expand current node label
                if (node && node.labelFull) {{
                    nodes.update({{id: nodeId, label: node.labelFull}});
                    selectedNodeId = nodeId;
                }}
                
                showNodeInfo(node);
            }} else {{
                // Click on canvas - restore labels
                if (selectedNodeId) {{
                    const node = nodes.get(selectedNodeId);
                    if (node && node.labelFull) {{
                        const shortLabel = node.labelFull.length > 30 
                            ? node.labelFull.substring(0, 28) + '…' 
                            : node.labelFull;
                        nodes.update({{id: selectedNodeId, label: shortLabel}});
                    }}
                    selectedNodeId = null;
                }}
                document.getElementById('info').classList.remove('active');
            }}
        }});
        
        function showNodeInfo(node) {{
            const info = document.getElementById('info');
            const title = document.getElementById('infoTitle');
            const table = document.getElementById('infoTable');
            
            const fullLabel = node.labelFull || node.label;
            title.textContent = `${{node.group}}: ${{fullLabel}}`;
            
            let rows = '';
            if (node.properties) {{
                const props = Object.keys(node.properties).sort();
                props.forEach(key => {{
                    const value = node.properties[key];
                    if (value !== null && value !== undefined) {{
                        rows += `<tr><th>${{key}}</th><td>${{value}}</td></tr>`;
                    }}
                }});
            }}
            
            table.innerHTML = rows || '<tr><td colspan="2" style="text-align:center;color:#97a6ba;">No properties</td></tr>';
            info.classList.add('active');
        }}
        
        function resetView() {{
            network.fit({{
                animation: {{
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }}
            }});
        }}
        
        function togglePhysics() {{
            physicsEnabled = !physicsEnabled;
            network.setOptions({{ physics: physicsEnabled }});
            const btn = document.getElementById('physicsBtn');
            btn.textContent = physicsEnabled ? '⏸ Pause Physics' : '▶ Play Physics';
        }}
        
        function toggleFullscreen() {{
            const btn = document.getElementById('fullscreenBtn');
            
            // Try native fullscreen first
            if (!document.fullscreenElement && document.documentElement.requestFullscreen) {{
                document.documentElement.requestFullscreen()
                    .then(() => {{
                        btn.textContent = '⛶ Exit Fullscreen';
                    }})
                    .catch(err => {{
                        // Fallback: use expanded mode
                        console.log('Fullscreen not available, using expanded mode');
                        toggleExpandedMode();
                    }});
            }} else if (document.fullscreenElement) {{
                document.exitFullscreen()
                    .then(() => {{
                        btn.textContent = '⛶ Fullscreen';
                    }})
                    .catch(err => {{
                        console.error('Error exiting fullscreen:', err);
                    }});
            }} else {{
                // Fullscreen not supported, use expanded mode
                toggleExpandedMode();
            }}
        }}
        
        let isExpanded = false;
        function toggleExpandedMode() {{
            const btn = document.getElementById('fullscreenBtn');
            isExpanded = !isExpanded;
            
            if (isExpanded) {{
                document.body.classList.add('expanded');
                btn.textContent = '⛶ Exit Expand';
            }} else {{
                document.body.classList.remove('expanded');
                btn.textContent = '⛶ Fullscreen';
            }}
            
            // Trigger network resize
            setTimeout(() => {{
                network.fit();
            }}, 100);
        }}
        
        // Listen for fullscreen changes (e.g., ESC key)
        document.addEventListener('fullscreenchange', function() {{
            const btn = document.getElementById('fullscreenBtn');
            if (btn) {{
                btn.textContent = document.fullscreenElement ? '⛶ Exit Fullscreen' : '⛶ Fullscreen';
            }}
        }});
        
        document.addEventListener('keydown', function(e) {{
            if (e.code === 'Space' && e.target.tagName !== 'INPUT') {{
                e.preventDefault();
                togglePhysics();
            }}
            // F key for fullscreen/expand
            if (e.code === 'KeyF' && !e.ctrlKey && !e.metaKey && e.target.tagName !== 'INPUT') {{
                e.preventDefault();
                toggleFullscreen();
            }}
            // ESC key for expanded mode
            if (e.code === 'Escape' && isExpanded) {{
                toggleExpandedMode();
            }}
        }});
        
        setTimeout(() => {{
            network.fit();
        }}, 100);
    </script>
</body>
</html>
    """
    return html

def _create_tooltip(node: dict) -> str:
    """Create a clean tooltip for nodes"""
    props = _serialize_properties(node["_props"])
    group = node["group"]
    
    lines = [f"<b>{group}</b>"]
    for key in sorted(props.keys())[:5]:
        value = props[key]
        if value is not None and str(value).strip():
            lines.append(f"{key}: {value}")
    
    return "<br>".join(lines)

def _safe_eid(obj, fallback_prefix="x"):
    """Return element_id if available; otherwise a stable fallback string"""
    if obj is None:
        return f"{fallback_prefix}_none"
    eid = getattr(obj, "element_id", None)
    if eid:
        return str(eid)
    for attr in ("start_node_element_id", "end_node_element_id"):
        if hasattr(obj, attr):
            try:
                val = getattr(obj, attr)
                if val:
                    return str(val)
            except Exception:
                pass
    return f"{fallback_prefix}_{abs(hash(repr(obj)))%10**12}"

def _add_node(n: Node, nodes_map: dict):
    """Add a node to the nodes map"""
    nid = _safe_eid(n, "n")
    if nid in nodes_map:
        return
    
    labels = list(getattr(n, "labels", []))
    main_label = labels[0] if labels else "Node"
    props = dict(n)
    
    # Select the most relevant field based on node type
    caption_full = None
    
    if main_label == "Stamp":
        # For stamps, show catalog_no
        caption_full = props.get("catalog_no")
        
    elif main_label == "Variety":
        # For varieties, show base_catalog_no + suffix (e.g., "1a")
        base = props.get("base_catalog_no", "")
        suffix = props.get("suffix", "")
        if base and suffix:
            caption_full = f"{base}{suffix}"
        elif base:
            caption_full = base
            
    elif main_label in ("Specimen", "Essay"):
        # For specimens and essays, show code
        caption_full = props.get("code")
        
    elif main_label in ("Proof", "DieProof", "PlateProof", "ColorProof"):
        # For all proof types, show code
        caption_full = props.get("code")
        
    elif main_label == "Issue":
        # For issues, prefer title over issue_id
        caption_full = props.get("title") or props.get("issue_id")
        
    elif main_label == "Person":
        caption_full = props.get("name")
        
    elif main_label == "Printer":
        caption_full = props.get("name")
        
    elif main_label == "LegalAct":
        # For documents, show type + id
        doc_type = props.get("type", "")
        doc_id = props.get("id", "")
        if doc_type and doc_id:
            caption_full = f"{doc_type} {doc_id}"
        else:
            caption_full = doc_type or doc_id
            
    elif main_label == "Plate":
        # For plates, try to build a descriptive name
        denom = props.get("denomination", "")
        plate_no = props.get("no", "")
        if denom and plate_no:
            caption_full = f"Plate {plate_no} ({denom})"
        elif plate_no:
            caption_full = f"Plate {plate_no}"
            
    elif main_label == "PlatePosition":
        # For plate positions, show position
        pos = props.get("pos")
        if pos:
            caption_full = f"Pos {pos}"
            
    elif main_label == "ProductionOrder":
        # Show date
        caption_full = props.get("date")
        
    elif main_label == "Quantity":
        # Show plate_desc or quantity
        caption_full = props.get("plate_desc") or f"Qty: {props.get('quantity', '')}"
        
    elif main_label == "RemaindersEvent":
        # Show date
        caption_full = props.get("date") or "Remainders"
    
    # Fallback to generic field search if nothing found
    if not caption_full:
        for key in ["name", "title", "code", "id"]:
            if key in props and props[key]:
                caption_full = str(props[key])
                break
    
    # Final fallback to label
    if not caption_full:
        caption_full = main_label
    
    # Convert to string and create short version
    caption_full = str(caption_full)
    caption_short = caption_full
    if len(caption_full) > 30:
        caption_short = caption_full[:28] + "…"
    
    # Get color
    color = PALETTE.get(main_label, "#8892a6")
    
    nodes_map[nid] = {
        "id": nid,
        "caption": caption_short,
        "caption_full": caption_full,
        "group": main_label,
        "color": color,
        "_props": props
    }

def _add_rel(r: Relationship, rels_map: dict):
    """Add a relationship to the rels map (avoids duplicates)"""
    try:
        start_node = getattr(r, "start_node", None)
        end_node = getattr(r, "end_node", None)
    except Exception:
        start_node = end_node = None
    
    s_id = _safe_eid(start_node, "s")
    e_id = _safe_eid(end_node, "t")
    rid = _safe_eid(r, "r")
    
    # Check if relationship already exists
    if rid in rels_map:
        return  # Skip duplicate
    
    rtype = getattr(r, "type", "")
    props = dict(r)
    
    serialized_props = _serialize_properties(props)
    
    title_parts = [f"<b>{rtype}</b>"]
    for k, v in serialized_props.items():
        if v is not None:
            title_parts.append(f"{k}: {v}")
    
    rels_map[rid] = {
        "id": rid,
        "from": s_id,
        "to": e_id,
        "label": rtype,
        "title": "<br>".join(title_parts),
        "properties": serialized_props
    }

# ======== Gradio UI ========
TITLE = "Costa Rica Postal Catalogue — Neo4j Graph Viewer"
HERO_MD = """
# 🎨 Neo4j Graph Visualization

**POSTAL CATALOGUE — COSTA RICA**

Interactive graph visualization with modern force-directed layout powered by **vis.js**. Type your **Cypher** query below and click **Render** to explore your data.

✨ **Features:** Fast rendering • Color-coded node types • Interactive tooltips • Physics simulation • Optimized for thousands of nodes
"""

with gr.Blocks(
    title=TITLE,
    theme=gr.themes.Soft(
        primary_hue="blue",
        neutral_hue="slate"
    ),
    css="""
        .gradio-container {
            max-width: 100% !important;
            padding: 20px !important;
        }
        #cypher-input textarea {
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace !important;
            font-size: 13px !important;
            line-height: 1.5 !important;
        }
        .render-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            border: none !important;
            font-weight: 600 !important;
            font-size: 15px !important;
        }
    """
) as demo:
    gr.Markdown(HERO_MD)
    
    with gr.Row():
        cypher = gr.Textbox(
            label="🔍 Cypher Query",
            value=DEFAULT_CYPHER,
            lines=7,
            placeholder="e.g. MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 200",
            elem_id="cypher-input"
        )
    
    with gr.Row():
        run_btn = gr.Button("🚀 Render Graph", size="lg", elem_classes="render-btn")
    
    with gr.Row():
        out_html = gr.HTML(label="Graph Visualization")
    
    gr.Markdown("""
    ---
    **💡 Tips:**
    - **Click on nodes** to expand labels and see full properties
    - **Click on canvas** to deselect and restore short labels
    - Use **mouse wheel** to zoom in/out
    - **Drag** to pan around the graph
    - Click **"Reset View"** to fit all nodes
    - Press **Space** to toggle physics simulation
    - Click **"Fullscreen"** or press **F** for fullscreen mode
    - Physics auto-pauses after stabilization for optimal performance
    """)
    
    run_btn.click(run_cypher, inputs=[cypher], outputs=[out_html])
    cypher.submit(run_cypher, inputs=[cypher], outputs=[out_html])

if __name__ == "__main__":
    share_flag = os.getenv("GRADIO_SHARE", "1")
    do_share = share_flag not in ("0", "false", "False")

    app_user = os.getenv("APP_USER")
    app_pass = os.getenv("APP_PASS")
    auth_pair = (app_user, app_pass) if app_user and app_pass else None

    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        share=do_share,
        auth=auth_pair,
    )