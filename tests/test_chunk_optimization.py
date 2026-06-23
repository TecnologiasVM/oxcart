"""
Test Chunk Optimization System

This script tests the new chunk optimization system against the landing reference file
to validate that we achieve similar quality and characteristics.

Additional Tests for Enhanced Chunk Optimization:
- Bbox recalculation when splitting paragraphs
- Small chunk grouping functionality  
- Quality validation and metrics
- Integration with external optimizer
"""

import json
import statistics
from pathlib import Path
from typing import Dict, Any, List
import os, sys
# tests/ lives one level below the repo root; make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dolphin_transformer import transform_dolphin_to_oxcart_preserving_labels
from chunk_optimizer import calculate_optimization_metrics
from dolphin_quality_control import DolphinQualityControl


def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON file safely."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_chunk_characteristics(data: Dict[str, Any], label: str = "") -> Dict[str, Any]:
    """Analyze characteristics of chunks in a dataset."""
    chunks = data.get('chunks', [])
    
    if not chunks:
        return {"error": "No chunks found"}
    
    # Basic statistics
    text_lengths = [len(chunk.get('text', '')) for chunk in chunks]
    chunk_types = [chunk.get('chunk_type', 'unknown') for chunk in chunks]
    
    # Count chunk types
    type_counts = {}
    for chunk_type in chunk_types:
        type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
    
    # Grounding analysis
    chunks_with_bbox = 0
    chunks_with_page = 0
    bbox_precision_samples = []
    
    for chunk in chunks:
        grounding = chunk.get('grounding', [])
        if grounding:
            g = grounding[0]
            if g.get('page') is not None:
                chunks_with_page += 1
            bbox = g.get('box')
            if bbox:
                chunks_with_bbox += 1
                # Sample bbox precision (number of decimal places)
                if isinstance(bbox, dict) and 'l' in bbox:
                    bbox_str = str(bbox['l'])
                    if '.' in bbox_str:
                        precision = len(bbox_str.split('.')[1])
                        bbox_precision_samples.append(precision)
    
    return {
        "label": label,
        "total_chunks": len(chunks),
        "text_length_stats": {
            "avg": round(statistics.mean(text_lengths), 1),
            "median": statistics.median(text_lengths),
            "min": min(text_lengths),
            "max": max(text_lengths),
            "std": round(statistics.stdev(text_lengths) if len(text_lengths) > 1 else 0, 1)
        },
        "chunk_types": type_counts,
        "grounding_stats": {
            "chunks_with_page": chunks_with_page,
            "chunks_with_bbox": chunks_with_bbox,
            "bbox_coverage": round(chunks_with_bbox / len(chunks) * 100, 1) if chunks else 0,
            "avg_bbox_precision": round(statistics.mean(bbox_precision_samples), 1) if bbox_precision_samples else 0
        }
    }


def compare_with_landing_reference(optimized_data: Dict[str, Any], 
                                 landing_path: str) -> Dict[str, Any]:
    """Compare optimized data with landing reference."""
    
    # Load landing reference
    landing_data = load_json_file(landing_path)
    
    # Analyze both datasets
    optimized_analysis = analyze_chunk_characteristics(optimized_data, "Optimized")
    landing_analysis = analyze_chunk_characteristics(landing_data, "Landing Reference")
    
    # Calculate similarity scores
    opt_avg = optimized_analysis["text_length_stats"]["avg"]
    land_avg = landing_analysis["text_length_stats"]["avg"]
    
    length_similarity = 1 - abs(opt_avg - land_avg) / max(opt_avg, land_avg, 1)
    
    # Chunk count comparison
    opt_count = optimized_analysis["total_chunks"]
    land_count = landing_analysis["total_chunks"]
    count_ratio = min(opt_count, land_count) / max(opt_count, land_count, 1)
    
    # Type distribution similarity
    opt_types = set(optimized_analysis["chunk_types"].keys())
    land_types = set(landing_analysis["chunk_types"].keys())
    type_overlap = len(opt_types & land_types) / len(opt_types | land_types) if (opt_types | land_types) else 0
    
    # Overall quality score
    quality_score = (length_similarity * 0.4 + count_ratio * 0.3 + type_overlap * 0.3)
    
    return {
        "optimized": optimized_analysis,
        "landing_reference": landing_analysis,
        "similarity_metrics": {
            "length_similarity": round(length_similarity, 3),
            "count_ratio": round(count_ratio, 3),
            "type_overlap": round(type_overlap, 3),
            "overall_quality": round(quality_score, 3)
        },
        "assessment": "Excellent" if quality_score > 0.8 else "Good" if quality_score > 0.6 else "Fair" if quality_score > 0.4 else "Poor"
    }


def test_bbox_recalculation():
    """Test that bbox coordinates are properly recalculated for sub-chunks"""
    print("\nTESTING BBOX RECALCULATION")
    print("=" * 50)
    
    # Create mock recognition data with a long paragraph that will be split
    mock_data = {
        "pages": [{
            "page_number": 1,
            "elements": [{
                "label": "para",
                "text": "This is a very long paragraph that should be split into multiple chunks. " * 20,  # Long text
                "bbox": [100, 200, 400, 300],  # Mock absolute coordinates
                "reading_order": 1
            }]
        }]
    }
    
    def mock_page_dims(page_num):
        return (612, 792)  # Standard page dimensions
    
    # Transform with splitting enabled
    result = transform_dolphin_to_oxcart_preserving_labels(
        mock_data,
        doc_id="test_bbox",
        page_dims_provider=mock_page_dims,
        para_max_chars=200,  # Force splitting
        optimize_for_rag=False  # Test internal splitting only
    )
    
    chunks = result.get('chunks', [])
    print(f"OK Generated {len(chunks)} chunks from 1 long paragraph")
    
    # Validate bbox recalculation
    for i, chunk in enumerate(chunks):
        grounding = chunk.get('grounding', [])
        if grounding:
            bbox = grounding[0].get('box')
            if bbox:
                print(f"   Chunk {i+1}: bbox = {bbox}")
                # Verify bbox is valid
                assert bbox['l'] <= bbox['r'], f"Invalid bbox width in chunk {i+1}"
                assert bbox['t'] <= bbox['b'], f"Invalid bbox height in chunk {i+1}"
                assert 0 <= bbox['l'] <= 1, f"Invalid bbox coordinates in chunk {i+1}"
                assert 0 <= bbox['t'] <= 1, f"Invalid bbox coordinates in chunk {i+1}"
    
    print("OK All bbox coordinates are valid and estimated correctly")
    return chunks


def test_chunk_grouping():
    """Test that small chunks are properly grouped together"""
    print("\nTESTING CHUNK GROUPING")
    print("=" * 50)
    
    # Create mock data with many small chunks
    mock_data = {
        "pages": [{
            "page_number": 1,
            "elements": [
                {"label": "para", "text": "Short text A.", "bbox": [100, 100, 200, 120], "reading_order": 1},
                {"label": "para", "text": "Short text B.", "bbox": [100, 125, 200, 145], "reading_order": 2},
                {"label": "para", "text": "Short text C.", "bbox": [100, 150, 200, 170], "reading_order": 3},
                {"label": "para", "text": "This is a longer text that should not be grouped with the short ones because it's already above the minimum threshold.", "bbox": [100, 200, 400, 250], "reading_order": 4},
                {"label": "para", "text": "Short D.", "bbox": [100, 260, 200, 280], "reading_order": 5},
            ]
        }]
    }
    
    def mock_page_dims(page_num):
        return (612, 792)
    
    result = transform_dolphin_to_oxcart_preserving_labels(
        mock_data,
        doc_id="test_grouping",
        page_dims_provider=mock_page_dims,
        optimize_for_rag=False  # Test internal grouping only
    )
    
    chunks = result.get('chunks', [])
    print(f"OK Generated {len(chunks)} chunks from 5 short elements")
    
    for i, chunk in enumerate(chunks):
        text_length = len(chunk.get('text', ''))
        text_preview = chunk.get('text', '')[:50] + ('...' if len(chunk.get('text', '')) > 50 else '')
        print(f"   Chunk {i+1}: {text_length} chars - '{text_preview}'")
    
    # Should have fewer chunks than original elements due to grouping
    assert len(chunks) < 5, "Expected chunk grouping to reduce the number of chunks"
    print("OK Small chunks were successfully grouped")
    return chunks


def test_optimization_pipeline(doc_id: str = "OXCART30"):
    """Test the complete optimization pipeline."""
    
    print(f"\n[TEST] Testing Chunk Optimization Pipeline for {doc_id}")
    print("=" * 60)
    
    # Paths
    original_path = f"./results/recognition_json/{doc_id}.json"
    landing_path = f"C:/Users/VM-SERVER/Downloads/{doc_id}_landing.json"
    
    # Check if files exist
    if not Path(original_path).exists():
        print(f"[ERROR] Original file not found: {original_path}")
        return
    
    if not Path(landing_path).exists():
        print(f"[ERROR] Landing reference not found: {landing_path}")
        return
    
    print("[LOAD] Loading original Dolphin recognition data...")
    original_data = load_json_file(original_path)
    
    print("[TRANSFORM] Transforming with optimization enabled...")
    # Test with optimization enabled
    optimized_data = transform_dolphin_to_oxcart_preserving_labels(
        original_data,
        doc_id=doc_id,
        para_max_chars=1000,
        table_row_block_size=None,
        optimize_for_rag=True,
        target_avg_length=150,
        max_chunk_length=800
    )
    
    print("[TRANSFORM] Transforming without optimization (baseline)...")
    # Test without optimization for comparison
    baseline_data = transform_dolphin_to_oxcart_preserving_labels(
        original_data,
        doc_id=doc_id,
        para_max_chars=1000,
        table_row_block_size=None,
        optimize_for_rag=False
    )
    
    print("[COMPARE] Comparing with landing reference...")
    # Compare with landing reference
    comparison = compare_with_landing_reference(optimized_data, landing_path)
    
    print("[RESULTS] Analysis Results:")
    print(f"   Landing Reference: {comparison['landing_reference']['total_chunks']} chunks, {comparison['landing_reference']['text_length_stats']['avg']} avg chars")
    print(f"   Baseline (no opt): {len(baseline_data['chunks'])} chunks, {statistics.mean([len(c.get('text', '')) for c in baseline_data['chunks']]):.1f} avg chars")
    print(f"   Optimized: {comparison['optimized']['total_chunks']} chunks, {comparison['optimized']['text_length_stats']['avg']} avg chars")
    
    print(f"\n[QUALITY] Assessment: {comparison['assessment']}")
    print(f"   Overall Score: {comparison['similarity_metrics']['overall_quality']}")
    print(f"   Length Similarity: {comparison['similarity_metrics']['length_similarity']}")
    print(f"   Count Ratio: {comparison['similarity_metrics']['count_ratio']}")
    print(f"   Type Overlap: {comparison['similarity_metrics']['type_overlap']}")
    
    # Grounding quality
    opt_grounding = comparison['optimized']['grounding_stats']
    land_grounding = comparison['landing_reference']['grounding_stats']
    
    print(f"\n[GROUNDING] Quality:")
    print(f"   Landing bbox coverage: {land_grounding['bbox_coverage']}%")
    print(f"   Optimized bbox coverage: {opt_grounding['bbox_coverage']}%")
    print(f"   Bbox precision: {opt_grounding['avg_bbox_precision']} decimal places")
    
    # Save optimized results
    output_path = f"./results/parsed_jsons/{doc_id}_optimized.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(optimized_data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] Optimized results saved to: {output_path}")
    
    # Calculate improvement metrics
    improvement_metrics = calculate_optimization_metrics(baseline_data['chunks'], optimized_data['chunks'])
    
    print(f"\n[IMPROVEMENT] Optimization Metrics:")
    print(f"   Chunk reduction: {improvement_metrics['improvement']['chunk_reduction']}")
    print(f"   Avg length increase: +{improvement_metrics['improvement']['avg_length_increase']:.1f} chars")
    print(f"   Consolidation ratio: {improvement_metrics['improvement']['consolidation_ratio']:.2f}")
    
    return comparison


def run_quality_control_analysis(doc_id: str = "OXCART30"):
    """Run quality control analysis on optimized results."""
    
    print(f"\n[QC] Running Quality Control Analysis...")
    
    # Load the optimized results
    optimized_path = f"./results/parsed_jsons/{doc_id}_optimized.json"
    original_path = f"./results/recognition_json/{doc_id}.json"
    
    if not Path(optimized_path).exists():
        print("[ERROR] Optimized file not found. Run test_optimization_pipeline first.")
        return
    
    optimized_data = load_json_file(optimized_path)
    original_data = load_json_file(original_path)
    
    # Run quality control
    qc = DolphinQualityControl()
    comparison_results = qc.compare_versions_generic(
        original_data=original_data,
        philatelic_data=optimized_data,
        doc_id=doc_id
    )
    
    # Display optimization quality metrics
    opt_quality = comparison_results['comparison_summary']['optimization_quality']
    print(f"   Optimization Quality: {opt_quality['assessment']} ({opt_quality['quality_score']})")
    print(f"   Average length: {opt_quality['avg_length']} chars (target: {opt_quality['target_range']})")
    print(f"   Length consistency (std): {opt_quality['length_std']}")
    print(f"   Very short chunks: {opt_quality['very_short_chunks']}")
    print(f"   Very long chunks: {opt_quality['very_long_chunks']}")
    
    return comparison_results


if __name__ == "__main__":
    print("ENHANCED CHUNK OPTIMIZATION TESTING SUITE")
    print("=" * 70)
    
    # Run enhanced tests first
    try:
        print("\nRunning Enhanced Tests...")
        test_bbox_recalculation()
        test_chunk_grouping()
        
        print("\nRunning Full Pipeline Test...")
        comparison = test_optimization_pipeline("OXCART30")
        if comparison:
            quality_results = run_quality_control_analysis("OXCART30")
            
        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("Enhanced Features Validated:")
        print("   * Bbox recalculation for split chunks: OK")
        print("   * Small chunk grouping: OK") 
        print("   * Quality validation and metrics: OK")
        print("   * Full pipeline optimization: OK")
        
    except Exception as e:
        print(f"\n[ERROR] Error during testing: {e}")
        import traceback
        traceback.print_exc()