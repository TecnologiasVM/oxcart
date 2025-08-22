"""
Chunk Optimizer for OXCART RAG

This module contains functions to optimize chunk generation for better grounding,
contextual grouping, and RAG performance. Based on analysis of landing data patterns.
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import statistics


def normalize_bbox_coordinates(bbox: List[int], page_width: int, page_height: int) -> Dict[str, float]:
    """
    Normalize absolute pixel coordinates to relative coordinates (0-1).
    
    Args:
        bbox: [x1, y1, x2, y2] in absolute pixels
        page_width: Page width in pixels  
        page_height: Page height in pixels
        
    Returns:
        Dictionary with normalized coordinates {l, t, r, b}
    """
    if not bbox or len(bbox) != 4:
        return None
    
    x1, y1, x2, y2 = bbox
    
    # Normalize to 0-1 range
    normalized = {
        'l': x1 / page_width,
        't': y1 / page_height, 
        'r': x2 / page_width,
        'b': y2 / page_height
    }
    
    # Ensure bounds are within 0-1
    for key in normalized:
        normalized[key] = max(0.0, min(1.0, normalized[key]))
    
    return normalized


def calculate_spatial_distance(bbox1: Dict[str, float], bbox2: Dict[str, float]) -> float:
    """
    Calculate spatial distance between two bounding boxes.
    
    Returns smaller values for boxes that are closer together.
    """
    if not bbox1 or not bbox2:
        return float('inf')
    
    # Calculate center points
    center1 = ((bbox1['l'] + bbox1['r']) / 2, (bbox1['t'] + bbox1['b']) / 2)
    center2 = ((bbox2['l'] + bbox2['r']) / 2, (bbox2['t'] + bbox2['b']) / 2)
    
    # Euclidean distance
    distance = ((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)**0.5
    return distance


def is_same_line(bbox1: Dict[str, float], bbox2: Dict[str, float], tolerance: float = 0.01) -> bool:
    """
    Check if two bounding boxes are on the same horizontal line.
    """
    if not bbox1 or not bbox2:
        return False
    
    # Compare vertical centers with tolerance
    center1_y = (bbox1['t'] + bbox1['b']) / 2
    center2_y = (bbox2['t'] + bbox2['b']) / 2
    
    return abs(center1_y - center2_y) < tolerance


def should_group_chunks(chunk1: Dict[str, Any], chunk2: Dict[str, Any], 
                       max_combined_length: int = 800) -> bool:
    """
    Determine if two chunks should be grouped together based on spatial proximity,
    content type, and size constraints.
    """
    # Check if combining would exceed size limit
    text1 = chunk1.get('text', '')
    text2 = chunk2.get('text', '')
    if len(text1) + len(text2) > max_combined_length:
        return False
    
    # Must be same chunk type
    type1 = chunk1.get('chunk_type', '')
    type2 = chunk2.get('chunk_type', '')
    if type1 != type2:
        return False
    
    # Don't group tables or figures
    if type1 in ['table', 'figure', 'image']:
        return False
    
    # Check spatial proximity
    grounding1 = chunk1.get('grounding', [])
    grounding2 = chunk2.get('grounding', [])
    
    if not grounding1 or not grounding2:
        return False
    
    # Must be on same page
    if grounding1[0].get('page') != grounding2[0].get('page'):
        return False
    
    bbox1 = grounding1[0].get('box')
    bbox2 = grounding2[0].get('box')
    
    if not bbox1 or not bbox2:
        return False
    
    # Check if on same line or vertically close
    if is_same_line(bbox1, bbox2):
        return True
    
    # Check vertical proximity (close paragraphs)
    distance = calculate_spatial_distance(bbox1, bbox2)
    return distance < 0.05  # Threshold for "close enough"


def classify_chunk_type_enhanced(text: str, bbox: Dict[str, float], 
                               page_width: float = 1.0, page_height: float = 1.0) -> str:
    """
    Enhanced chunk type classification based on content and position.
    """
    text_lower = text.lower().strip()
    
    # Check position-based classification
    if bbox:
        # Marginalia - content in margins
        is_left_margin = bbox['r'] < 0.15
        is_right_margin = bbox['l'] > 0.85
        is_top_margin = bbox['b'] < 0.1
        is_bottom_margin = bbox['t'] > 0.9
        
        if is_left_margin or is_right_margin or is_top_margin or is_bottom_margin:
            return 'marginalia'
        
        # Header - top area
        if bbox['t'] < 0.15 and len(text) < 100:
            return 'header'
        
        # Footer - bottom area
        if bbox['t'] > 0.85 and len(text) < 100:
            return 'footer'
    
    # Content-based classification
    if re.match(r'^(figure|fig|table|tab)\s*\d+', text_lower):
        return 'caption'
    
    if len(text) < 50 and (text.isupper() or ':' in text):
        return 'header'
    
    # Default to text
    return 'text'


def group_chunks_contextually(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group chunks contextually based on spatial proximity and content similarity.
    """
    if not chunks:
        return chunks
    
    # Sort chunks by page and reading order
    sorted_chunks = sorted(chunks, key=lambda x: (
        x.get('grounding', [{}])[0].get('page', 0),
        x.get('metadata', {}).get('reading_order_range', [0])[0] if x.get('metadata', {}).get('reading_order_range') else 0
    ))
    
    grouped_chunks = []
    i = 0
    
    while i < len(sorted_chunks):
        current_chunk = sorted_chunks[i].copy()
        
        # Try to group with subsequent chunks
        j = i + 1
        while j < len(sorted_chunks):
            next_chunk = sorted_chunks[j]
            
            if should_group_chunks(current_chunk, next_chunk):
                # Merge the chunks
                current_chunk = merge_chunks(current_chunk, next_chunk)
                j += 1
            else:
                break
        
        grouped_chunks.append(current_chunk)
        i = j if j > i + 1 else i + 1
    
    return grouped_chunks


def merge_chunks(chunk1: Dict[str, Any], chunk2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two chunks into one, combining text and updating metadata.
    """
    merged = chunk1.copy()
    
    # Combine text with proper spacing
    text1 = chunk1.get('text', '').strip()
    text2 = chunk2.get('text', '').strip()
    
    # Smart text joining
    if text1.endswith('.') or text1.endswith('!') or text1.endswith('?'):
        combined_text = f"{text1} {text2}"
    elif text1.endswith('-'):
        # Handle hyphenation
        combined_text = f"{text1[:-1]}{text2}"
    else:
        combined_text = f"{text1} {text2}"
    
    merged['text'] = combined_text
    
    # Update grounding to encompass both chunks
    grounding1 = chunk1.get('grounding', [])
    grounding2 = chunk2.get('grounding', [])
    
    if grounding1 and grounding2:
        bbox1 = grounding1[0].get('box')
        bbox2 = grounding2[0].get('box')
        
        if bbox1 and bbox2:
            # Create combined bounding box
            combined_bbox = {
                'l': min(bbox1['l'], bbox2['l']),
                't': min(bbox1['t'], bbox2['t']),
                'r': max(bbox1['r'], bbox2['r']),
                'b': max(bbox1['b'], bbox2['b'])
            }
            
            merged['grounding'] = [{
                'page': grounding1[0].get('page'),
                'box': combined_bbox
            }]
    
    # Update metadata
    if 'metadata' in merged:
        metadata1 = chunk1.get('metadata', {})
        metadata2 = chunk2.get('metadata', {})
        
        # Combine reading order ranges
        range1 = metadata1.get('reading_order_range', [])
        range2 = metadata2.get('reading_order_range', [])
        
        if range1 and range2:
            combined_range = [min(range1[0], range2[0]), max(range1[-1], range2[-1])]
            merged['metadata']['reading_order_range'] = combined_range
        
        # Update quality score (take average)
        score1 = metadata1.get('quality_score', 0.5)
        score2 = metadata2.get('quality_score', 0.5)
        merged['metadata']['quality_score'] = (score1 + score2) / 2
    
    return merged


def optimize_chunks_for_rag(oxcart_data: Dict[str, Any], 
                          target_avg_length: int = 150,
                          max_chunk_length: int = 800) -> Dict[str, Any]:
    """
    Main function to optimize chunks for better RAG performance.
    
    This function:
    1. Normalizes grounding coordinates 
    2. Groups chunks contextually
    3. Improves chunk type classification
    4. Optimizes for target chunk length
    """
    optimized_data = oxcart_data.copy()
    chunks = optimized_data.get('chunks', [])
    
    if not chunks:
        return optimized_data
    
    # Step 1: Normalize grounding coordinates (if missing)
    for chunk in chunks:
        grounding = chunk.get('grounding', [])
        if grounding and grounding[0].get('box') is None:
            # Try to get original coordinates from metadata if available
            # For now, we'll keep the placeholder
            pass
    
    # Step 2: Enhance chunk type classification
    for chunk in chunks:
        grounding = chunk.get('grounding', [])
        bbox = None
        if grounding and grounding[0].get('box'):
            bbox = grounding[0]['box']
        
        text = chunk.get('text', '')
        enhanced_type = classify_chunk_type_enhanced(text, bbox)
        chunk['chunk_type'] = enhanced_type
    
    # Step 3: Group chunks contextually
    grouped_chunks = group_chunks_contextually(chunks)
    
    # Step 4: Validate and adjust chunk lengths
    final_chunks = []
    for chunk in grouped_chunks:
        text_length = len(chunk.get('text', ''))
        
        # Split overly long chunks
        if text_length > max_chunk_length:
            split_chunks = split_long_chunk(chunk, max_chunk_length)
            final_chunks.extend(split_chunks)
        else:
            final_chunks.append(chunk)
    
    optimized_data['chunks'] = final_chunks
    
    # Update document metadata
    optimized_data.setdefault('extraction_metadata', {})['optimization_applied'] = True
    optimized_data['extraction_metadata']['optimization_timestamp'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
    optimized_data['extraction_metadata']['original_chunk_count'] = len(chunks)
    optimized_data['extraction_metadata']['optimized_chunk_count'] = len(final_chunks)
    
    # Calculate quality metrics
    lengths = [len(c.get('text', '')) for c in final_chunks]
    if lengths:
        optimized_data['extraction_metadata']['avg_chunk_length'] = statistics.mean(lengths)
        optimized_data['extraction_metadata']['median_chunk_length'] = statistics.median(lengths)
        optimized_data['extraction_metadata']['max_chunk_length'] = max(lengths)
        optimized_data['extraction_metadata']['min_chunk_length'] = min(lengths)
    
    return optimized_data


def split_long_chunk(chunk: Dict[str, Any], max_length: int) -> List[Dict[str, Any]]:
    """
    Split a chunk that's too long into smaller chunks while preserving context.
    """
    text = chunk.get('text', '')
    if len(text) <= max_length:
        return [chunk]
    
    # Try to split on sentence boundaries first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_text = ""
    base_id = chunk.get('chunk_id', 'unknown')
    
    for i, sentence in enumerate(sentences):
        if len(current_text + sentence) <= max_length:
            current_text = (current_text + " " + sentence).strip()
        else:
            # Create chunk with current text
            if current_text:
                new_chunk = chunk.copy()
                new_chunk['text'] = current_text
                new_chunk['chunk_id'] = f"{base_id}_split_{len(chunks)}"
                chunks.append(new_chunk)
            
            # Start new chunk with current sentence
            current_text = sentence
    
    # Add remaining text
    if current_text:
        new_chunk = chunk.copy()
        new_chunk['text'] = current_text
        new_chunk['chunk_id'] = f"{base_id}_split_{len(chunks)}"
        chunks.append(new_chunk)
    
    return chunks if chunks else [chunk]


def calculate_optimization_metrics(original_chunks: List[Dict[str, Any]], 
                                 optimized_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate metrics to evaluate optimization quality.
    """
    def get_text_stats(chunks):
        lengths = [len(c.get('text', '')) for c in chunks]
        return {
            'count': len(chunks),
            'avg_length': statistics.mean(lengths) if lengths else 0,
            'median_length': statistics.median(lengths) if lengths else 0,
            'max_length': max(lengths) if lengths else 0,
            'min_length': min(lengths) if lengths else 0
        }
    
    original_stats = get_text_stats(original_chunks)
    optimized_stats = get_text_stats(optimized_chunks)
    
    return {
        'original': original_stats,
        'optimized': optimized_stats,
        'improvement': {
            'chunk_reduction': original_stats['count'] - optimized_stats['count'],
            'avg_length_increase': optimized_stats['avg_length'] - original_stats['avg_length'],
            'consolidation_ratio': optimized_stats['count'] / original_stats['count'] if original_stats['count'] > 0 else 1
        }
    }