"""
Generic script to run quality control checks for any document
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from dolphin_quality_control import DolphinQualityControl

def run_simple_check(doc_id: str = "OXCART22"):
    """Run quality control check for a specific document."""
    qc = DolphinQualityControl()
    
    print(f"Analyzing document: {doc_id}")
    print("Loading original recognition data...")
    
    # Load and compare
    try:
        original_data = qc.load_original_recognition(doc_id)
        print(f"Original elements: {sum(len(p.get('elements', [])) for p in original_data.get('pages', []))}")
        
        # Try different file naming patterns
        try:
            existing_data = qc.load_philatelic_results(doc_id)
        except FileNotFoundError:
            # Try alternative naming
            import json
            alt_path = qc.parsed_jsons_dir / f"{doc_id}_philatelic.json"
            if alt_path.exists():
                with open(alt_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                print(f"Using {doc_id}_philatelic.json")
            else:
                raise FileNotFoundError("No philatelic results found")
        print(f"Existing chunks: {len(existing_data.get('chunks', []))}")
        
        # Analyze existing oversized chunks
        oversized_existing = []
        for chunk in existing_data.get('chunks', []):
            if len(chunk.get('text', '')) > 1500:
                oversized_existing.append({
                    'id': chunk.get('chunk_id', ''),
                    'type': chunk.get('chunk_type', ''),
                    'size': len(chunk.get('text', ''))
                })
        
        print(f"Existing oversized chunks: {len(oversized_existing)}")
        for chunk in oversized_existing:
            print(f"  - {chunk['id']} ({chunk['type']}): {chunk['size']} chars")
        
        # Generate fresh parsing
        print("Generating fresh parsing with updated transformer...")
        fresh_data = qc.generate_fresh_philatelic_parsing(doc_id)
        print(f"Fresh chunks: {len(fresh_data.get('chunks', []))}")
        
        # Analyze fresh oversized chunks
        oversized_fresh = []
        for chunk in fresh_data.get('chunks', []):
            if len(chunk.get('text', '')) > 1500:
                oversized_fresh.append({
                    'id': chunk.get('chunk_id', ''),
                    'type': chunk.get('chunk_type', ''),
                    'size': len(chunk.get('text', ''))
                })
        
        print(f"Fresh oversized chunks: {len(oversized_fresh)}")
        for chunk in oversized_fresh:
            print(f"  - {chunk['id']} ({chunk['type']}): {chunk['size']} chars")
        
        improvement = len(oversized_existing) - len(oversized_fresh)
        print(f"Improvement: {improvement:+d} chunks")
        
        if len(oversized_fresh) == 0:
            print("RESULT: PASS - No oversized chunks in fresh version")
        elif improvement > 0:
            print(f"RESULT: IMPROVEMENT - Reduced oversized chunks by {improvement}")
        else:
            print("RESULT: NEEDS WORK - Still has oversized chunks")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def run_generic_check(original_data, philatelic_data, doc_id: str):
    """Run quality control check using provided data objects."""
    qc = DolphinQualityControl()
    
    print(f"Analyzing document: {doc_id} (using provided data)")
    
    try:
        # Use the generic comparison method
        comparison = qc.compare_versions_generic(original_data, philatelic_data, doc_id)
        
        original_stats = comparison['original']
        philatelic_stats = comparison['philatelic']
        summary = comparison['comparison_summary']
        
        print(f"Original elements: {original_stats['total_elements']}")
        print(f"Philatelic chunks: {philatelic_stats['total_chunks']}")
        print(f"Element to chunk ratio: {summary['element_to_chunk_ratio']:.2f}")
        
        oversized_count = len(philatelic_stats['oversized_chunks'])
        print(f"Oversized chunks: {oversized_count}")
        
        if oversized_count > 0:
            print("Oversized chunks details:")
            for chunk in philatelic_stats['oversized_chunks']:
                print(f"  - {chunk['chunk_id']} ({chunk['chunk_type']}): {chunk['text_length']} chars")
        
        # Generate quality assessment
        if oversized_count == 0:
            print("RESULT: PASS - No oversized chunks")
            return True
        elif oversized_count <= original_stats['total_elements'] * 0.05:  # Less than 5% of original elements
            print(f"RESULT: ACCEPTABLE - {oversized_count} oversized chunks (<5% of original elements)")
            return True
        else:
            print(f"RESULT: NEEDS IMPROVEMENT - Too many oversized chunks ({oversized_count})")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    
    # Check if document ID is provided as argument
    if len(sys.argv) > 1:
        doc_id = sys.argv[1]
        run_simple_check(doc_id)
    else:
        # Default to OXCART22
        run_simple_check()