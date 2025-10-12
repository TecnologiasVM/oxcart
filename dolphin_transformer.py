"""
Dolphin Document Transformer

This module contains functions to transform Dolphin recognition results into OXCART format
with improved table handling and chunk generation for RAG applications.
"""

import re
import uuid
from typing import Any, Callable, Dict, List, Tuple, Optional
from datetime import datetime
from pathlib import Path


def _validate_html_table(html: str) -> bool:
    """Validate if HTML contains a reasonable table structure."""
    if not html or len(html.strip()) < 20:
        return False
    
    # Check for basic table structure
    if not re.search(r'<table[^>]*>', html, re.I):
        return False
    
    # Count rows and cells to detect malformed tables
    rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.I | re.S)
    if len(rows) > 200:  # Too many rows
        return False
        
    if len(rows) < 2:  # Need at least header + data row
        return False
    
    # Check for reasonable cell structure
    total_cells = len(re.findall(r'<t[dh][^>]*>.*?</t[dh]>', html, re.I | re.S))
    if total_cells > 1000:  # Too many cells
        return False
    
    # Detect repetitive malformed tables (like the "Genus" problem)
    cell_contents = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', html, re.I | re.S)
    cleaned_contents = [re.sub(r'<.*?>', '', cell).strip() for cell in cell_contents if cell.strip()]
    
    # If more than 70% of cells contain the same text, it's likely malformed
    if cleaned_contents:
        from collections import Counter
        content_counts = Counter(cleaned_contents)
        most_common = content_counts.most_common(1)[0]
        if most_common[1] / len(cleaned_contents) > 0.7:
            print(f"Warning: Table appears malformed - {most_common[1]}/{len(cleaned_contents)} cells contain '{most_common[0]}'")
            return False
    
    # Check for mostly empty tables (too many empty cells)
    empty_cells = len([cell for cell in cleaned_contents if not cell or cell in ['', 'nan']])
    if empty_cells / max(1, len(cleaned_contents)) > 0.8:
        print(f"Warning: Table appears malformed - {empty_cells}/{len(cleaned_contents)} cells are empty")
        return False
    
    return True


def _table_to_md_tsv_and_sentences(html: str, context_title: str = None) -> Dict[str, Any]:
    """
    Convert HTML table to markdown/TSV format and extract row sentences.
    Includes strict validation and size limits to prevent oversized chunks.
    
    Args:
        html: HTML table string
        context_title: Optional context title to prepend to sentences
        
    Returns:
        Dictionary containing markdown, tsv, headers, and row_sentences
    """
    # Validate input
    if not _validate_html_table(html):
        print("Warning: Invalid or malformed table HTML detected, skipping.")
        return {"markdown": None, "tsv": None, "headers": [], "row_sentences": []}
    
    headers, markdown, tsv, row_sentences = [], None, None, []

    try:
        import pandas as pd
        from io import StringIO
        
        # Use StringIO to avoid pandas deprecation warning
        dfs = pd.read_html(StringIO(html))
        if not dfs:
            raise ValueError("No tables parsed")
        df = dfs[0]
        
        # Validate dataframe size
        if df.shape[0] > 100 or df.shape[1] > 25:
            raise ValueError(f"Table too large: {df.shape[0]} rows x {df.shape[1]} columns")

        # Clean headers/values to strings and limit length
        df = df.map(lambda x: "" if x is None else str(x)[:200])  # Limit cell content

        # Extract and clean headers
        headers = [str(c)[:50] for c in df.columns.tolist()]  # Limit header length
        
        # Validate headers
        if len(headers) == 0 or all(h.strip() == "" for h in headers):
            raise ValueError("No valid headers found")

        # Generate markdown if available
        if hasattr(df, "to_markdown"):
            try:
                markdown = df.to_markdown(index=False)
                # Validate markdown size
                if len(markdown) > 8000:
                    print(f"Warning: Markdown too large ({len(markdown)} chars), truncating")
                    markdown = markdown[:8000] + "\n... (truncated)"
            except Exception:
                markdown = None
        
        # Generate TSV (always available)
        tsv = df.to_csv(index=False, sep="\t")
        if len(tsv) > 8000:
            print(f"Warning: TSV too large ({len(tsv)} chars), truncating")
            tsv = tsv[:8000] + "\n... (truncated)"

        # Generate sentences per row with size control
        for idx, (_, row) in enumerate(df.iterrows()):
            if idx >= 50:  # Limit number of row sentences
                break
                
            parts = []
            for col in df.columns:
                val = str(row[col]).strip()
                if val != "" and val != "nan":
                    # Limit individual field length
                    if len(val) > 100:
                        val = val[:100] + "..."
                    parts.append(f"{col}: {val}")
            
            if parts:
                sent = ", ".join(parts)
                if len(sent) > 500:  # Limit sentence length
                    sent = sent[:500] + "..."
                if context_title:
                    sent = f"{context_title} — " + sent
                row_sentences.append(sent)

    except Exception as e:
        # Strict fallback: only process well-formed simple tables
        print(f"Warning: Pandas table parsing failed: {e}. Using strict fallback parser.")
        
        # Extract rows with strict validation
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I|re.S)
        if len(rows) > 50:  # Much stricter row limit
            print(f"Warning: Too many rows ({len(rows)}), skipping table")
            return {"markdown": None, "tsv": None, "headers": [], "row_sentences": []}
        
        simple_rows = []
        for r in rows[:50]:  # Process max 50 rows
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.I|re.S)
            # Clean and limit cell content
            cells = [re.sub(r"<.*?>", "", c).strip()[:100] for c in cells]  # Limit cell length
            cells = [c for c in cells if c]  # Remove empty cells
            
            if cells and len(cells) <= 10:  # Much stricter column limit
                simple_rows.append(cells)

        if len(simple_rows) < 2:  # Need at least header + 1 data row
            print("Warning: Insufficient table data, skipping")
            return {"markdown": None, "tsv": None, "headers": [], "row_sentences": []}
            
        headers = simple_rows[0][:10]  # Limit headers
        data_rows = simple_rows[1:30]  # Limit data rows
        
        # Validate headers
        if not headers or all(not h.strip() for h in headers):
            print("Warning: No valid headers found, skipping table")
            return {"markdown": None, "tsv": None, "headers": [], "row_sentences": []}
        
        # Generate TSV with size control
        tsv_lines = ["\t".join(headers)]
        for r in data_rows:
            # Pad/truncate row to match header count
            r_clean = [c.replace("\t", " ").replace("\n", " ").strip() for c in r]
            r_padded = (r_clean + [""] * len(headers))[:len(headers)]
            tsv_lines.append("\t".join(r_padded))
            
            # Generate sentence with strict limits
            parts = []
            for col, val in zip(headers, r_padded):
                if val and val.strip():
                    val_clean = val.strip()[:80]  # Limit value length
                    parts.append(f"{col}: {val_clean}")
            
            if parts:
                sent = ", ".join(parts)
                if len(sent) > 400:  # Strict sentence limit
                    sent = sent[:400] + "..."
                if context_title:
                    sent = f"{context_title} — " + sent
                row_sentences.append(sent)
        
        tsv = "\n".join(tsv_lines)
        
        # Validate TSV size
        if len(tsv) > 5000:
            print(f"Warning: TSV still too large ({len(tsv)} chars), truncating")
            tsv = tsv[:5000] + "\n... (truncated)"
        
        # Generate simple markdown with size control
        if headers and len(data_rows) > 0:
            try:
                sep = "| " + " | ".join("---" for _ in headers) + " |"
                md_head = "| " + " | ".join(h[:30] for h in headers) + " |"  # Limit header display
                md_rows = []
                
                for r in data_rows[:20]:  # Limit displayed rows
                    r_clean = [c.replace("|", "\|").strip()[:30] for c in r]  # Escape pipes, limit length
                    padded = (r_clean + [""] * len(headers))[:len(headers)]
                    md_rows.append("| " + " | ".join(padded) + " |")
                
                markdown = "\n".join([md_head, sep] + md_rows)
                
                # Final size check
                if len(markdown) > 6000:
                    print(f"Warning: Markdown too large ({len(markdown)} chars), truncating")
                    markdown = markdown[:6000] + "\n... (truncated)"
                    
            except Exception as md_error:
                print(f"Warning: Markdown generation failed: {md_error}")
                markdown = None

    # Ensure strings
    if markdown is not None:
        markdown = str(markdown)
    if tsv is not None:
        tsv = str(tsv)

    return {
        "markdown": markdown,
        "tsv": tsv,
        "headers": headers,
        "row_sentences": row_sentences
    }


def _simplify_html_table(html: str) -> str:
    """
    Simplify HTML table to a readable text format for LLMs as a last resort.

    Args:
        html: HTML table string

    Returns:
        Simplified text representation of the table
    """
    if not html or len(html.strip()) < 20:
        return ""

    try:
        # Extract rows with minimal processing
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I|re.S)
        if not rows or len(rows) > 50:  # Limit to reasonable size
            return ""

        simplified_rows = []
        for i, row in enumerate(rows[:20]):  # Process max 20 rows
            # Extract cells
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I|re.S)
            # Clean cell content
            cells = [re.sub(r"<.*?>", "", cell).strip()[:80] for cell in cells]
            cells = [cell for cell in cells if cell]  # Remove empty cells

            if cells and len(cells) <= 8:  # Reasonable column limit
                if i == 0:  # Header row
                    simplified_rows.append("Headers: " + " | ".join(cells))
                else:
                    simplified_rows.append(f"Row {i}: " + " | ".join(cells))

        if len(simplified_rows) >= 2:  # At least header + 1 data row
            result = "\n".join(simplified_rows)
            # Ensure reasonable size
            if len(result) > 1500:
                result = result[:1500] + "\n... (truncated)"
            return result

    except Exception as e:
        print(f"Warning: HTML table simplification failed: {e}")

    return ""


def _normalize_box(bbox: List[float], w: Optional[int], h: Optional[int]) -> Optional[Dict[str, float]]:
    """
    Normalize bounding box coordinates to relative values.
    
    Args:
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        w: Page width
        h: Page height
        
    Returns:
        Normalized bounding box or None if invalid
    """
    if not bbox or w in (None, 0) or h in (None, 0):
        return None
    x1, y1, x2, y2 = bbox
    return {
        "l": round(x1/w, 6), 
        "t": round(y1/h, 6), 
        "r": round(x2/w, 6), 
        "b": round(y2/h, 6)
    }


def _group_small_chunks(chunks: List[Dict[str, Any]], min_chunk_size: int = 100, max_combined_size: int = 1200) -> List[Dict[str, Any]]:
    """
    Group small consecutive chunks to avoid having too many tiny chunks.
    
    Args:
        chunks: List of chunks to process
        min_chunk_size: Minimum size threshold for chunks
        max_combined_size: Maximum size when combining chunks
        
    Returns:
        List of optimized chunks with small ones grouped together
    """
    if not chunks:
        return chunks
    
    optimized_chunks = []
    i = 0
    
    while i < len(chunks):
        current_chunk = chunks[i].copy()
        current_text = current_chunk.get('text', '')
        
        # If current chunk is large enough, keep it as is
        if len(current_text) >= min_chunk_size:
            optimized_chunks.append(current_chunk)
            i += 1
            continue
        
        # Try to combine small chunks
        combined_text = current_text
        combined_bbox = current_chunk.get('grounding', [{}])[0].get('box')
        reading_order_start = current_chunk.get('metadata', {}).get('reading_order_range', [0])[0]
        reading_order_end = reading_order_start
        j = i + 1
        
        # Look for consecutive small chunks to combine
        while (j < len(chunks) and 
               len(combined_text) < max_combined_size and
               len(chunks[j].get('text', '')) < min_chunk_size * 2):  # Don't absorb medium chunks
            
            next_chunk = chunks[j]
            next_text = next_chunk.get('text', '')
            
            # Check if they're compatible for merging
            if (_can_merge_chunks(current_chunk, next_chunk) and 
                len(combined_text + ' ' + next_text) <= max_combined_size):
                
                # Combine text
                combined_text = (combined_text + ' ' + next_text).strip()
                
                # Update bbox to encompass both
                next_bbox = next_chunk.get('grounding', [{}])[0].get('box')
                if combined_bbox and next_bbox:
                    combined_bbox = {
                        'l': min(combined_bbox['l'], next_bbox['l']),
                        't': min(combined_bbox['t'], next_bbox['t']),
                        'r': max(combined_bbox['r'], next_bbox['r']),
                        'b': max(combined_bbox['b'], next_bbox['b'])
                    }
                
                # Update reading order range
                next_ro = next_chunk.get('metadata', {}).get('reading_order_range', [0])
                if next_ro:
                    reading_order_end = next_ro[-1]
                
                j += 1
            else:
                break
        
        # Create the combined chunk
        current_chunk['text'] = combined_text
        if combined_bbox:
            current_chunk['grounding'] = [{
                'page': current_chunk.get('grounding', [{}])[0].get('page'),
                'box': combined_bbox
            }]
        
        # Update metadata
        if 'metadata' in current_chunk:
            current_chunk['metadata']['reading_order_range'] = [reading_order_start, reading_order_end]
            current_chunk['metadata']['combined_chunks'] = j - i
        
        optimized_chunks.append(current_chunk)
        i = j
    
    return optimized_chunks


def _can_merge_chunks(chunk1: Dict[str, Any], chunk2: Dict[str, Any]) -> bool:
    """
    Check if two chunks can be safely merged.
    
    Args:
        chunk1: First chunk
        chunk2: Second chunk
        
    Returns:
        True if chunks can be merged
    """
    # Must be same type
    if chunk1.get('chunk_type') != chunk2.get('chunk_type'):
        return False
    
    # Don't merge tables, figures, or captions
    chunk_type = chunk1.get('chunk_type', '')
    if chunk_type in ['table', 'figure', 'caption', 'table_row']:
        return False
    
    # Must be on same page
    page1 = chunk1.get('grounding', [{}])[0].get('page')
    page2 = chunk2.get('grounding', [{}])[0].get('page')
    if page1 != page2:
        return False
    
    # Check reading order proximity
    ro1 = chunk1.get('metadata', {}).get('reading_order_range', [])
    ro2 = chunk2.get('metadata', {}).get('reading_order_range', [])
    
    if ro1 and ro2:
        # Should be consecutive or very close in reading order
        gap = ro2[0] - ro1[-1]
        if gap > 5:  # Too far apart in reading order
            return False
    
    return True


def _estimate_sub_bbox(original_bbox: Dict[str, float], text_part: str, full_text: str, part_index: int) -> Dict[str, float]:
    """
    Estimate bounding box for a sub-chunk based on text position within original bbox.
    
    Args:
        original_bbox: Original bbox coordinates {l, t, r, b}
        text_part: Text content of this sub-chunk
        full_text: Complete original text
        part_index: Index of this part (0, 1, 2...)
        
    Returns:
        Estimated bbox for the sub-chunk
    """
    if not original_bbox or not text_part or not full_text:
        return original_bbox
    
    # Calculate relative position based on text length
    part_length = len(text_part)
    full_length = len(full_text)
    
    if full_length == 0:
        return original_bbox
    
    # Estimate vertical position (assuming text flows top to bottom)
    bbox_height = original_bbox['b'] - original_bbox['t']
    relative_start = sum(len(p) for p in full_text.split()[:part_index * 20]) / full_length  # Rough estimation
    relative_size = part_length / full_length
    
    # Calculate new bbox
    estimated_bbox = {
        'l': original_bbox['l'],  # Keep same horizontal bounds
        'r': original_bbox['r'],
        't': original_bbox['t'] + (relative_start * bbox_height),
        'b': min(original_bbox['b'], original_bbox['t'] + ((relative_start + relative_size) * bbox_height))
    }
    
    # Ensure bounds are valid
    if estimated_bbox['t'] >= estimated_bbox['b']:
        estimated_bbox['b'] = estimated_bbox['t'] + 0.01  # Minimum height
    
    return estimated_bbox


def _split_long_paragraph(text: str, max_chars: int = 1200, overlap_sents: int = 1) -> List[str]:
    """
    Split long paragraphs into smaller chunks with sentence overlap.
    
    Args:
        text: Input text to split
        max_chars: Maximum characters per chunk
        overlap_sents: Number of sentences to overlap between chunks
        
    Returns:
        List of text chunks
    """
    txt = re.sub(r"\s+", " ", (text or "").strip())
    if len(txt) <= max_chars: 
        return [txt] if txt else []
    
    sents = re.split(r'(?<=[\.!?])\s+', txt)
    chunks, i = [], 0
    
    while i < len(sents):
        acc, total, j = [], 0, i
        while j < len(sents) and total + len(sents[j]) + 1 <= max_chars:
            acc.append(sents[j])
            total += len(sents[j]) + 1
            j += 1
        
        if not acc: 
            acc = [sents[i]]
            j = i + 1
        
        chunks.append(" ".join(acc).strip())
        i = max(i + 1, j - overlap_sents)
    
    return chunks


def _validate_and_enhance_chunks(oxcart_data: Dict[str, Any]) -> None:
    """
    Validate and enhance chunks with quality metrics and final checks.
    
    Args:
        oxcart_data: OXCART data structure to validate and enhance
    """
    chunks = oxcart_data.get('chunks', [])
    if not chunks:
        return
    
    # Calculate quality metrics
    total_chunks = len(chunks)
    total_text_length = sum(len(c.get('text', '')) for c in chunks)
    lengths = [len(c.get('text', '')) for c in chunks]
    
    # Count chunks by type
    type_counts = {}
    quality_issues = 0
    
    for chunk in chunks:
        chunk_type = chunk.get('chunk_type', 'unknown')
        type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
        
        # Validate chunk quality
        text = chunk.get('text', '')
        text_length = len(text)
        
        # Flag potential quality issues
        if text_length < 10:  # Very short chunks
            quality_issues += 1
        elif text_length > 2000:  # Very long chunks
            quality_issues += 1
        
        # Ensure bbox validity
        grounding = chunk.get('grounding', [])
        if grounding and grounding[0].get('box'):
            bbox = grounding[0]['box']
            if bbox:
                # Fix any bbox coordinate issues
                if bbox.get('l', 0) > bbox.get('r', 1):
                    bbox['l'], bbox['r'] = bbox['r'], bbox['l']
                if bbox.get('t', 0) > bbox.get('b', 1):
                    bbox['t'], bbox['b'] = bbox['b'], bbox['t']
                
                # Ensure bounds are within 0-1
                for coord in ['l', 't', 'r', 'b']:
                    bbox[coord] = max(0.0, min(1.0, bbox[coord]))
    
    # Add quality metadata
    oxcart_data.setdefault('extraction_metadata', {}).update({
        'chunk_count': total_chunks,
        'total_text_length': total_text_length,
        'avg_chunk_length': total_text_length / total_chunks if total_chunks > 0 else 0,
        'max_chunk_length': max(lengths) if lengths else 0,
        'min_chunk_length': min(lengths) if lengths else 0,
        'chunk_types': type_counts,
        'quality_issues': quality_issues,
        'validation_applied': True
    })
    
    print(f"OK Validation complete: {total_chunks} chunks, {quality_issues} quality issues detected")


def transform_dolphin_to_oxcart_preserving_labels(
    recognition_results: Any,
    doc_id: str = "doc",
    page_dims_provider: Optional[Callable[[int], Tuple[int, int]]] = None,
    exclude_labels: Tuple[str, ...] = ("header", "foot"),
    para_max_chars: int = 1500,  # Increased from 1200 to 1500 for better alignment with ideal
    fuse_figure_and_caption: bool = True,
    table_row_block_size: Optional[int] = None,  # Disabled by default to preserve table integrity
    strict_mode: bool = True,  # New parameter for strict validation
    optimize_for_rag: bool = True,  # Enable chunk optimization
    target_avg_length: int = 300,  # Increased from 150 to 300 for better alignment with ideal
    max_chunk_length: int = 1200  # Increased from 800 to 1200 for longer contextual chunks
) -> Dict[str, Any]:
    """
    Transform Dolphin recognition results to OXCART format with enhanced table handling.
    
    Args:
        recognition_results: Dolphin model output (pages with elements)
        doc_id: Document identifier
        page_dims_provider: Function to get page dimensions (page_num) -> (width, height)
        exclude_labels: Labels to exclude from processing
        para_max_chars: Maximum characters per paragraph chunk
        fuse_figure_and_caption: Whether to combine figures with their captions
        table_row_block_size: Number of table row sentences per chunk (None=disabled to preserve table integrity)
        strict_mode: Enable strict validation and size limits
        
    Returns:
        OXCART format dictionary with chunks and metadata
    """
    # Normalize input to list of pages
    if isinstance(recognition_results, dict) and "pages" in recognition_results:
        pages_in = recognition_results["pages"]
    elif isinstance(recognition_results, list) and recognition_results and isinstance(recognition_results[0], dict) and "page_number" in recognition_results[0]:
        pages_in = recognition_results
    elif isinstance(recognition_results, list) and recognition_results and isinstance(recognition_results[0], dict):
        pages_in = [{"page_number": 1, "elements": recognition_results}]
    else:
        raise ValueError("Unrecognized format for recognition_results")

    # Initialize OXCART structure
    oxcart = {
        "doc_id": doc_id,
        "source": "dolphin",
        "page_count": len(pages_in),
        "extraction_date": datetime.utcnow().isoformat() + "Z",
        "metadata": {"title": "", "author": "", "language": "und"},
        "chunks": [],
        "markdown": ""
    }

    # Label mapping from Dolphin to OXCART types
    DOLPHIN2TYPE = {
        "title": "title",
        "sec": "section",
        "sub_sec": "subsection",
        "para": "text",
        "tab": "table",
        "fig": "figure",
        "cap": "caption",
        "fnote": "marginalia",
        "header": "header",
        "foot": "marginalia"
    }

    md_parts = []
    chunk_counter = 0

    for page in pages_in:
        pno = int(page.get("page_number", 1))
        elements = sorted(page.get("elements", []), key=lambda e: e.get("reading_order", 0))

        # Get page dimensions if provider is available
        w = h = None
        if page_dims_provider:
            try:
                w, h = page_dims_provider(pno)
            except Exception:
                w = h = None

        skip_next = False
        for idx, el in enumerate(elements):
            if skip_next:
                skip_next = False
                continue

            label = (el.get("label") or "").lower()
            
            # Skip excluded labels
            if label in exclude_labels:
                continue
                
            chunk_type = DOLPHIN2TYPE.get(label, "text")
            txt = (el.get("text") or "").strip()
            bbox = el.get("bbox")
            ro = el.get("reading_order", 0)
            bbox_norm = _normalize_box(bbox, w, h)

            # FIGURE with optional CAPTION fusion
            if label == "fig" and fuse_figure_and_caption:
                labels = [label]
                ro_end = ro
                cap_txt = None
                
                # Check if next element is a caption
                if idx + 1 < len(elements) and (elements[idx + 1].get("label","").lower() == "cap"):
                    cap = elements[idx + 1]
                    cap_txt = (cap.get("text") or "").strip()
                    ro_end = cap.get("reading_order", ro)
                    labels.append("cap")
                    skip_next = True
                
                vis_text = cap_txt if cap_txt else txt
                if vis_text:
                    md_parts.append(vis_text + "\n\n")
                
                chunk_counter += 1
                oxcart["chunks"].append({
                    "chunk_id": f"{doc_id}:{pno:03d}:{ro}-{ro_end}:0",
                    "chunk_type": "figure",
                    "text": vis_text,
                    "grounding": [{"page": pno, "box": bbox_norm}],
                    "metadata": {
                        "labels": labels,
                        "reading_order_range": [ro, ro_end],
                        "figure_path": el.get("figure_path")
                    }
                })
                continue

            # TABLE with strict processing and validation
            if label == "tab":
                # Strict size and content validation
                if not txt or len(txt.strip()) < 30:  # More strict minimum size
                    continue
                
                if len(txt) > 50000:  # Reject extremely large HTML
                    print(f"Warning: Skipping extremely large table HTML on page {pno} (size: {len(txt)} chars)")
                    continue
                
                # Check for reasonable table structure before processing
                if not _validate_html_table(txt):
                    print(f"Warning: Skipping malformed table on page {pno}")
                    continue

                # Convert table to multiple formats with strict validation
                conv = _table_to_md_tsv_and_sentences(txt, context_title=None)

                # Smart format selection - prioritize Markdown > TSV > Simplified HTML
                table_format = "unknown"
                if conv["markdown"]:
                    main_text = conv["markdown"]
                    table_format = "markdown"
                elif conv["tsv"]:
                    main_text = conv["tsv"]
                    table_format = "tsv"
                else:
                    # Last resort: simplify HTML for LLM readability
                    main_text = _simplify_html_table(txt)
                    table_format = "simplified_html"
                    if not main_text:
                        print(f"Warning: All table conversion methods failed on page {pno}, skipping")
                        continue
                
                # More strict size validation
                if len(main_text) > 3000:  # Much stricter limit
                    print(f"Warning: Skipping oversized table on page {pno} (size: {len(main_text)} chars)")
                    continue
                
                # Validate that we have meaningful content
                if len(conv["headers"]) == 0 or len(main_text.strip()) < 50:
                    print(f"Warning: Table lacks meaningful content on page {pno}, skipping")
                    continue

                # Main table chunk
                chunk_counter += 1
                table_chunk_id = f"{doc_id}:{pno:03d}:{ro}-{ro}:0"
                oxcart["chunks"].append({
                    "chunk_id": table_chunk_id,
                    "chunk_type": "table",
                    "text": main_text,
                    "grounding": [{"page": pno, "box": bbox_norm}],
                    "metadata": {
                        "labels": [label],
                        "reading_order_range": [ro, ro],
                        "table_format": table_format,  # Indicates which format was selected
                        "headers": conv["headers"],
                        "n_rows": len(conv["row_sentences"])
                    }
                })
                md_parts.append(main_text + "\n\n")

                # Additional chunks: row sentences (only if table_row_block_size is specified)
                if table_row_block_size is not None:
                    rsents = conv["row_sentences"] or []
                    
                    # Only create row chunks for tables with reasonable size and content
                    if rsents and len(rsents) > 3 and len(rsents) <= 30:  # Strict row count limits
                        # Very conservative block size
                        effective_block_size = min(table_row_block_size, 3)  # Max 3 rows per chunk
                        
                        for start in range(0, len(rsents), effective_block_size):
                            block = rsents[start:start+effective_block_size]
                            if not block:  # Skip empty blocks
                                continue
                            
                            block_text = "\n".join(block)
                            
                            # Very strict size limits for row chunks
                            if len(block_text) > 800:  # Much stricter limit
                                print(f"Warning: Skipping oversized table_row chunk on page {pno} (size: {len(block_text)} chars)")
                                continue
                            
                            # Quality check: ensure meaningful content
                            if len(block_text.strip()) < 20 or block_text.count(":") < 2:
                                continue  # Skip low-quality blocks
                                
                            chunk_counter += 1
                            oxcart["chunks"].append({
                                "chunk_id": f"{doc_id}:{pno:03d}:{ro}-{ro}:rows{start}",
                                "chunk_type": "table_row",
                                "text": block_text,
                                "grounding": [{"page": pno, "box": bbox_norm}],
                                "metadata": {
                                    "labels": [label, "table_row_sentences"],
                                    "reading_order_range": [ro, ro],
                                    "parent_table_chunk_id": table_chunk_id,
                                    "row_index_range": [start, min(start+effective_block_size, len(rsents))-1],
                                    "headers": conv["headers"],
                                    "quality_score": len(block_text.split(":")) / len(block)  # Simple quality metric
                                }
                            })
                    elif len(rsents) > 30:
                        print(f"Warning: Table has too many rows ({len(rsents)}) on page {pno}, skipping row chunks")
                else:
                    print(f"Info: Table row segmentation disabled, keeping table as single chunk on page {pno}")
                continue

            # CAPTION (standalone)
            if label == "cap":
                if txt:
                    md_parts.append(f"*{txt}*\n\n")
                    chunk_counter += 1
                    oxcart["chunks"].append({
                        "chunk_id": f"{doc_id}:{pno:03d}:{ro}-{ro}:0",
                        "chunk_type": "caption",
                        "text": txt,
                        "grounding": [{"page": pno, "box": bbox_norm}],
                        "metadata": {"labels":[label], "reading_order_range":[ro, ro]}
                    })
                continue

            # TEXT ELEMENTS (title, section, subsection, paragraph, footnote, etc.)
            if txt:
                # Split long paragraphs into smaller chunks
                if label == "para":
                    parts = _split_long_paragraph(txt, max_chars=para_max_chars, overlap_sents=1)
                else:
                    parts = [txt]
                
                for si, part in enumerate(parts):
                    # Add appropriate markdown formatting
                    if label == "title":
                        md_parts.append("# " + part + "\n\n")
                    elif label == "sec":
                        md_parts.append("## " + part + "\n\n")
                    elif label == "sub_sec":
                        md_parts.append("### " + part + "\n\n")
                    else:
                        md_parts.append(part + "\n\n")

                    # Estimate bbox for sub-chunks when text is split
                    part_bbox = bbox_norm
                    if len(parts) > 1 and bbox_norm:
                        part_bbox = _estimate_sub_bbox(bbox_norm, part, txt, si)

                    chunk_counter += 1
                    oxcart["chunks"].append({
                        "chunk_id": f"{doc_id}:{pno:03d}:{ro}-{ro}:{si}",
                        "chunk_type": DOLPHIN2TYPE.get(label, "text"),
                        "text": part,
                        "grounding": [{"page": pno, "box": part_bbox}],
                        "metadata": {
                            "labels": [label],
                            "reading_order_range": [ro, ro],
                            "part_index": si if len(parts) > 1 else None,
                            "quality_score": min(1.0, len(part) / 100)  # Simple quality metric
                        }
                    })

    # Finalize markdown
    oxcart["markdown"] = "".join(md_parts).strip()
    
    # Apply internal chunk grouping first (to reduce small chunks)
    if len(oxcart["chunks"]) > 0:
        print(f"Info: Applying internal chunk grouping to {len(oxcart['chunks'])} chunks")
        oxcart["chunks"] = _group_small_chunks(oxcart["chunks"], min_chunk_size=100, max_combined_size=1200)
        print(f"Info: After grouping: {len(oxcart['chunks'])} chunks")
    
    # Apply external chunk optimization if requested
    if optimize_for_rag:
        try:
            from chunk_optimizer import optimize_chunks_for_rag
            print(f"Info: Applying external RAG optimization")
            original_count = len(oxcart["chunks"])
            oxcart = optimize_chunks_for_rag(
                oxcart, 
                target_avg_length=target_avg_length,
                max_chunk_length=max_chunk_length
            )
            print(f"Info: External optimization: {original_count} → {len(oxcart['chunks'])} chunks")
        except ImportError:
            print("Warning: chunk_optimizer module not available, skipping external optimization")
        except Exception as e:
            print(f"Warning: External optimization failed: {e}")
    
    # Final validation and quality metrics
    _validate_and_enhance_chunks(oxcart)
    
    return oxcart