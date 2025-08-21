"""
Dolphin Quality Control System

This module provides quality control and comparison tools for analyzing 
the differences between original Dolphin parsing and the enhanced philatelic version.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
import statistics
from datetime import datetime

# Import the transformation functions
from dolphin_transformer import transform_dolphin_to_oxcart_preserving_labels
from philatelic_patterns import enrich_all_chunks_filatelia


class DolphinQualityControl:
    """Quality control system for Dolphin document parsing."""
    
    def __init__(self, results_dir: str = "./results"):
        self.results_dir = Path(results_dir)
        self.recognition_json_dir = self.results_dir / "recognition_json"
        self.parsed_jsons_dir = self.results_dir / "parsed_jsons"
        
    def load_original_recognition(self, doc_id: str) -> Dict[str, Any]:
        """Load original Dolphin recognition results."""
        json_path = self.recognition_json_dir / f"{doc_id}.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Original recognition file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_philatelic_results(self, doc_id: str) -> Dict[str, Any]:
        """Load enhanced philatelic results."""
        json_path = self.parsed_jsons_dir / f"{doc_id}.enriched.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Philatelic results file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def generate_fresh_philatelic_parsing(self, doc_id: str) -> Dict[str, Any]:
        """Generate fresh philatelic parsing from original recognition results."""
        original_data = self.load_original_recognition(doc_id)
        
        # Transform to OXCART format
        oxcart_data = transform_dolphin_to_oxcart_preserving_labels(
            original_data,
            doc_id=doc_id,
            para_max_chars=1000,
            table_row_block_size=5  # Use the new safer default
        )
        
        # Enrich with philatelic metadata
        enriched_data = enrich_all_chunks_filatelia(oxcart_data)
        
        return enriched_data
    
    def analyze_original_elements(self, original_data: Dict[str, Any]) -> Dict[str, Any]:
      """Analyze original Dolphin recognition elements."""
      # Handle both formats: list of pages or dict with "pages" key
      if isinstance(original_data, list):
          pages = original_data
      else:
          pages = original_data.get("pages", [])

      stats = {
          "total_pages": len(pages),
          "total_elements": 0,
          "elements_by_label": defaultdict(int),
          "elements_by_page": defaultdict(int),
          "text_lengths": [],
          "table_elements": [],
          "problematic_elements": []
      }

      for page in pages:
          page_num = page.get("page_number", 0)
          elements = page.get("elements", [])
          stats["elements_by_page"][page_num] = len(elements)
          stats["total_elements"] += len(elements)

          for element in elements:
              label = element.get("label", "unknown").lower()
              text = element.get("text", "")
              text_len = len(text)

              stats["elements_by_label"][label] += 1
              stats["text_lengths"].append(text_len)

              # Identify problematic elements
              if text_len > 5000:
                  stats["problematic_elements"].append({
                      "page": page_num,
                      "label": label,
                      "text_length": text_len,
                      "reading_order": element.get("reading_order", 0),
                      "text_preview": text[:200] + "..." if len(text) > 200 else text
                  })

              # Track table elements specifically
              if label == "tab":
                  stats["table_elements"].append({
                      "page": page_num,
                      "text_length": text_len,
                      "reading_order": element.get("reading_order", 0),
                      "html_preview": text[:500] + "..." if len(text) > 500 else text
                  })

      return stats
    
    def analyze_philatelic_chunks(self, philatelic_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze philatelic chunks."""
        stats = {
            "total_chunks": len(philatelic_data.get("chunks", [])),
            "chunks_by_type": defaultdict(int),
            "chunks_by_page": defaultdict(int),
            "text_lengths": [],
            "oversized_chunks": [],
            "table_chunks": [],
            "table_row_chunks": []
        }
        
        for chunk in philatelic_data.get("chunks", []):
            chunk_type = chunk.get("chunk_type", "unknown")
            text = chunk.get("text", "")
            text_len = len(text)
            chunk_id = chunk.get("chunk_id", "")
            
            # Extract page number from chunk_id
            page_match = re.search(r':(\d{3}):', chunk_id)
            page_num = int(page_match.group(1)) if page_match else 0
            
            stats["chunks_by_type"][chunk_type] += 1
            stats["chunks_by_page"][page_num] += 1
            stats["text_lengths"].append(text_len)
            
            # Identify oversized chunks
            if text_len > 1500:
                stats["oversized_chunks"].append({
                    "chunk_id": chunk_id,
                    "chunk_type": chunk_type,
                    "page": page_num,
                    "text_length": text_len,
                    "text_preview": text[:200] + "..." if len(text) > 200 else text,
                    "metadata": chunk.get("metadata", {})
                })
            
            # Track table-related chunks
            if chunk_type == "table":
                stats["table_chunks"].append({
                    "chunk_id": chunk_id,
                    "page": page_num,
                    "text_length": text_len,
                    "metadata": chunk.get("metadata", {})
                })
            elif chunk_type == "table_row":
                stats["table_row_chunks"].append({
                    "chunk_id": chunk_id,
                    "page": page_num,
                    "text_length": text_len,
                    "parent_table": chunk.get("metadata", {}).get("parent_table_chunk_id", ""),
                    "row_range": chunk.get("metadata", {}).get("row_index_range", [])
                })
        
        return stats
    
    def compare_versions(self, doc_id: str) -> Dict[str, Any]:
        """Compare original vs philatelic versions."""
        print(f"🔍 Analyzing document: {doc_id}")
        
        # Load data
        original_data = self.load_original_recognition(doc_id)
        
        try:
            existing_philatelic = self.load_philatelic_results(doc_id)
            print("📁 Using existing philatelic results")
        except FileNotFoundError:
            print("🔄 Generating fresh philatelic results")
            existing_philatelic = self.generate_fresh_philatelic_parsing(doc_id)
        
        # Generate fresh parsing for comparison
        fresh_philatelic = self.generate_fresh_philatelic_parsing(doc_id)
        
        # Analyze all versions
        original_stats = self.analyze_original_elements(original_data)
        existing_stats = self.analyze_philatelic_chunks(existing_philatelic)
        fresh_stats = self.analyze_philatelic_chunks(fresh_philatelic)
        
        comparison = {
            "doc_id": doc_id,
            "timestamp": datetime.now().isoformat(),
            "original": original_stats,
            "existing_philatelic": existing_stats,
            "fresh_philatelic": fresh_stats,
            "comparison_summary": self._generate_comparison_summary(
                original_stats, existing_stats, fresh_stats
            )
        }
        
        return comparison
    
    def compare_versions_generic(self, original_data: Dict[str, Any], philatelic_data: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
        """Compare original vs philatelic versions using provided data objects."""
        print(f"🔍 Analyzing document: {doc_id} (using provided data)")
        
        # Analyze both versions
        original_stats = self.analyze_original_elements(original_data)
        philatelic_stats = self.analyze_philatelic_chunks(philatelic_data)
        
        comparison = {
            "doc_id": doc_id,
            "timestamp": datetime.now().isoformat(),
            "original": original_stats,
            "philatelic": philatelic_stats,
            "comparison_summary": self._generate_comparison_summary_generic(
                original_stats, philatelic_stats
            )
        }
        
        return comparison
    
    def _generate_comparison_summary(self, original: Dict, existing: Dict, fresh: Dict) -> Dict[str, Any]:
        """Generate comparison summary between versions."""
        summary = {
            "element_to_chunk_ratio": {
                "existing": existing["total_chunks"] / original["total_elements"] if original["total_elements"] > 0 else 0,
                "fresh": fresh["total_chunks"] / original["total_elements"] if original["total_elements"] > 0 else 0
            },
            "oversized_chunks": {
                "existing_count": len(existing["oversized_chunks"]),
                "fresh_count": len(fresh["oversized_chunks"]),
                "improvement": len(existing["oversized_chunks"]) - len(fresh["oversized_chunks"])
            },
            "table_processing": {
                "original_tables": original["elements_by_label"]["tab"],
                "existing_table_chunks": existing["chunks_by_type"]["table"],
                "existing_table_row_chunks": existing["chunks_by_type"]["table_row"],
                "fresh_table_chunks": fresh["chunks_by_type"]["table"],
                "fresh_table_row_chunks": fresh["chunks_by_type"]["table_row"]
            },
            "text_length_stats": {
                "original_avg": statistics.mean(original["text_lengths"]) if original["text_lengths"] else 0,
                "original_max": max(original["text_lengths"]) if original["text_lengths"] else 0,
                "existing_avg": statistics.mean(existing["text_lengths"]) if existing["text_lengths"] else 0,
                "existing_max": max(existing["text_lengths"]) if existing["text_lengths"] else 0,
                "fresh_avg": statistics.mean(fresh["text_lengths"]) if fresh["text_lengths"] else 0,
                "fresh_max": max(fresh["text_lengths"]) if fresh["text_lengths"] else 0
            }
        }
        
        return summary
    
    def _generate_comparison_summary_generic(self, original: Dict, philatelic: Dict) -> Dict[str, Any]:
        """Generate comparison summary between original and philatelic versions."""
        summary = {
            "element_to_chunk_ratio": philatelic["total_chunks"] / original["total_elements"] if original["total_elements"] > 0 else 0,
            "oversized_chunks_count": len(philatelic["oversized_chunks"]),
            "table_processing": {
                "original_tables": original["elements_by_label"]["tab"],
                "philatelic_table_chunks": philatelic["chunks_by_type"]["table"],
                "philatelic_table_row_chunks": philatelic["chunks_by_type"]["table_row"]
            },
            "text_length_stats": {
                "original_avg": statistics.mean(original["text_lengths"]) if original["text_lengths"] else 0,
                "original_max": max(original["text_lengths"]) if original["text_lengths"] else 0,
                "philatelic_avg": statistics.mean(philatelic["text_lengths"]) if philatelic["text_lengths"] else 0,
                "philatelic_max": max(philatelic["text_lengths"]) if philatelic["text_lengths"] else 0
            }
        }
        
        return summary
    
    def generate_detailed_report(self, doc_id: str, output_file: Optional[str] = None) -> str:
        """Generate a detailed quality control report."""
        comparison = self.compare_versions(doc_id)
        return self._generate_report_content(comparison, output_file)
    
    def generate_detailed_report_generic(self, original_data: Dict[str, Any], philatelic_data: Dict[str, Any], doc_id: str, output_file: Optional[str] = None) -> str:
        """Generate a detailed quality control report using provided data objects."""
        comparison = self.compare_versions_generic(original_data, philatelic_data, doc_id)
        return self._generate_report_content_generic(comparison, output_file)
    
    def _generate_report_content(self, comparison: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """Generate report content for file-based comparison."""
        
        report_lines = [
            f"# Dolphin Quality Control Report",
            f"**Document:** {comparison['doc_id']}",
            f"**Generated:** {comparison['timestamp']}",
            "",
            "## Executive Summary",
            ""
        ]
        
        summary = comparison["comparison_summary"]
        
        # Oversized chunks analysis
        improvement = summary["oversized_chunks"]["improvement"]
        if improvement > 0:
            report_lines.append(f"✅ **Improvement:** Reduced oversized chunks by {improvement}")
        elif improvement < 0:
            report_lines.append(f"❌ **Regression:** Increased oversized chunks by {abs(improvement)}")
        else:
            report_lines.append(f"➖ **No change** in oversized chunks")
        
        report_lines.extend([
            "",
            "## Original Dolphin Elements",
            f"- Total elements: {comparison['original']['total_elements']}",
            f"- Total pages: {comparison['original']['total_pages']}",
            f"- Table elements: {comparison['original']['elements_by_label']['tab']}",
            f"- Average text length: {summary['text_length_stats']['original_avg']:.1f} chars",
            f"- Max text length: {summary['text_length_stats']['original_max']} chars",
            ""
        ])
        
        # Problematic original elements
        if comparison['original']['problematic_elements']:
            report_lines.append("### Problematic Original Elements (>5000 chars)")
            for elem in comparison['original']['problematic_elements']:
                report_lines.append(f"- Page {elem['page']}, {elem['label']}: {elem['text_length']} chars")
            report_lines.append("")
        
        # Existing vs Fresh comparison
        report_lines.extend([
            "## Philatelic Version Comparison",
            "",
            "| Metric | Existing | Fresh | Change |",
            "|--------|----------|-------|--------|",
            f"| Total chunks | {comparison['existing_philatelic']['total_chunks']} | {comparison['fresh_philatelic']['total_chunks']} | {comparison['fresh_philatelic']['total_chunks'] - comparison['existing_philatelic']['total_chunks']:+d} |",
            f"| Oversized chunks | {len(comparison['existing_philatelic']['oversized_chunks'])} | {len(comparison['fresh_philatelic']['oversized_chunks'])} | {len(comparison['fresh_philatelic']['oversized_chunks']) - len(comparison['existing_philatelic']['oversized_chunks']):+d} |",
            f"| Table chunks | {comparison['existing_philatelic']['chunks_by_type']['table']} | {comparison['fresh_philatelic']['chunks_by_type']['table']} | {comparison['fresh_philatelic']['chunks_by_type']['table'] - comparison['existing_philatelic']['chunks_by_type']['table']:+d} |",
            f"| Table row chunks | {comparison['existing_philatelic']['chunks_by_type']['table_row']} | {comparison['fresh_philatelic']['chunks_by_type']['table_row']} | {comparison['fresh_philatelic']['chunks_by_type']['table_row'] - comparison['existing_philatelic']['chunks_by_type']['table_row']:+d} |",
            f"| Avg text length | {summary['text_length_stats']['existing_avg']:.1f} | {summary['text_length_stats']['fresh_avg']:.1f} | {summary['text_length_stats']['fresh_avg'] - summary['text_length_stats']['existing_avg']:+.1f} |",
            f"| Max text length | {summary['text_length_stats']['existing_max']} | {summary['text_length_stats']['fresh_max']} | {summary['text_length_stats']['fresh_max'] - summary['text_length_stats']['existing_max']:+d} |",
            ""
        ])
        
        # Detailed oversized chunks analysis
        if comparison['existing_philatelic']['oversized_chunks']:
            report_lines.append("### Existing Oversized Chunks")
            for chunk in comparison['existing_philatelic']['oversized_chunks']:
                report_lines.append(f"- **{chunk['chunk_id']}** ({chunk['chunk_type']}): {chunk['text_length']} chars on page {chunk['page']}")
            report_lines.append("")
        
        if comparison['fresh_philatelic']['oversized_chunks']:
            report_lines.append("### Fresh Oversized Chunks")
            for chunk in comparison['fresh_philatelic']['oversized_chunks']:
                report_lines.append(f"- **{chunk['chunk_id']}** ({chunk['chunk_type']}): {chunk['text_length']} chars on page {chunk['page']}")
            report_lines.append("")
        
        # Table analysis
        report_lines.extend([
            "## Table Processing Analysis",
            f"Original had {comparison['original']['elements_by_label']['tab']} table elements",
            ""
        ])
        
        if comparison['original']['table_elements']:
            report_lines.append("### Original Table Elements")
            for table in comparison['original']['table_elements']:
                report_lines.append(f"- Page {table['page']}: {table['text_length']} chars")
            report_lines.append("")
        
        # Recommendations
        report_lines.extend([
            "## Recommendations",
            ""
        ])
        
        if len(comparison['fresh_philatelic']['oversized_chunks']) > 0:
            report_lines.append("❌ **Still has oversized chunks** - Consider further reducing table_row_block_size or adding more aggressive filtering")
        else:
            report_lines.append("✅ **No oversized chunks detected** - Current configuration is working well")
        
        if improvement > 0:
            report_lines.append("✅ **Quality improved** - The updated transformer is working better")
        elif improvement < 0:
            report_lines.append("❌ **Quality degraded** - Review the recent changes to the transformer")
        
        report_content = "\n".join(report_lines)
        
        # Save report if output file specified
        if output_file:
            Path(output_file).write_text(report_content, encoding='utf-8')
            print(f"📝 Report saved to: {output_file}")
        
        return report_content
    
    def _generate_report_content_generic(self, comparison: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """Generate report content for generic data comparison."""
        
        report_lines = [
            f"# Dolphin Quality Control Report",
            f"**Document:** {comparison['doc_id']}",
            f"**Generated:** {comparison['timestamp']}",
            "",
            "## Executive Summary",
            ""
        ]
        
        summary = comparison["comparison_summary"]
        
        # Oversized chunks analysis
        oversized_count = summary["oversized_chunks_count"]
        if oversized_count == 0:
            report_lines.append(f"✅ **No oversized chunks detected** - Quality is good")
        else:
            report_lines.append(f"⚠️ **Found {oversized_count} oversized chunks** - May need optimization")
        
        report_lines.extend([
            "",
            "## Original Dolphin Elements",
            f"- Total elements: {comparison['original']['total_elements']}",
            f"- Total pages: {comparison['original']['total_pages']}",
            f"- Table elements: {comparison['original']['elements_by_label']['tab']}",
            f"- Average text length: {summary['text_length_stats']['original_avg']:.1f} chars",
            f"- Max text length: {summary['text_length_stats']['original_max']} chars",
            ""
        ])
        
        # Problematic original elements
        if comparison['original']['problematic_elements']:
            report_lines.append("### Problematic Original Elements (>5000 chars)")
            for elem in comparison['original']['problematic_elements']:
                report_lines.append(f"- Page {elem['page']}, {elem['label']}: {elem['text_length']} chars")
            report_lines.append("")
        
        # Philatelic version analysis
        report_lines.extend([
            "## Philatelic Enhanced Version",
            f"- Total chunks: {comparison['philatelic']['total_chunks']}",
            f"- Element to chunk ratio: {summary['element_to_chunk_ratio']:.2f}",
            f"- Oversized chunks: {oversized_count}",
            f"- Table chunks: {comparison['philatelic']['chunks_by_type']['table']}",
            f"- Table row chunks: {comparison['philatelic']['chunks_by_type']['table_row']}",
            f"- Average text length: {summary['text_length_stats']['philatelic_avg']:.1f} chars",
            f"- Max text length: {summary['text_length_stats']['philatelic_max']} chars",
            ""
        ])
        
        # Detailed oversized chunks analysis
        if comparison['philatelic']['oversized_chunks']:
            report_lines.append("### Oversized Chunks")
            for chunk in comparison['philatelic']['oversized_chunks']:
                report_lines.append(f"- **{chunk['chunk_id']}** ({chunk['chunk_type']}): {chunk['text_length']} chars on page {chunk['page']}")
            report_lines.append("")
        
        # Table analysis
        report_lines.extend([
            "## Table Processing Analysis",
            f"Original had {comparison['original']['elements_by_label']['tab']} table elements",
            f"Transformed into {comparison['philatelic']['chunks_by_type']['table']} table chunks and {comparison['philatelic']['chunks_by_type']['table_row']} table row chunks",
            ""
        ])
        
        # Recommendations
        report_lines.extend([
            "## Recommendations",
            ""
        ])
        
        if oversized_count > 0:
            report_lines.append("❌ **Still has oversized chunks** - Consider reducing table_row_block_size or adding more aggressive filtering")
        else:
            report_lines.append("✅ **No oversized chunks detected** - Current configuration is working well")
        
        if summary['element_to_chunk_ratio'] > 2.0:
            report_lines.append("⚠️ **High chunk multiplication** - Consider increasing para_max_chars to reduce chunk fragmentation")
        elif summary['element_to_chunk_ratio'] < 0.5:
            report_lines.append("⚠️ **Low chunk count** - May be losing granularity, consider reducing para_max_chars")
        else:
            report_lines.append("✅ **Good chunk ratio** - Transformation is working well")
        
        report_content = "\n".join(report_lines)
        
        # Save report if output file specified
        if output_file:
            Path(output_file).write_text(report_content, encoding='utf-8')
            print(f"📝 Report saved to: {output_file}")
        
        return report_content
    
    def run_quality_check(self, doc_id: str) -> bool:
        """Run a quick quality check and return True if quality is acceptable."""
        comparison = self.compare_versions(doc_id)
        
        # Quality criteria
        existing_oversized = len(comparison['existing_philatelic']['oversized_chunks'])
        fresh_oversized = len(comparison['fresh_philatelic']['oversized_chunks'])
        improvement = existing_oversized - fresh_oversized
        
        print(f"\n🎯 Quality Check Results for {doc_id}:")
        print(f"   Existing oversized chunks: {existing_oversized}")
        print(f"   Fresh oversized chunks: {fresh_oversized}")
        print(f"   Improvement: {improvement:+d}")
        
        # Pass criteria: no oversized chunks in fresh version, or significant improvement
        quality_pass = fresh_oversized == 0 or improvement >= max(1, existing_oversized // 2)
        
        if quality_pass:
            print("   ✅ PASS - Quality is acceptable")
        else:
            print("   ❌ FAIL - Quality needs improvement")
        
        return quality_pass


def main():
    """Main function for running quality control checks."""
    qc = DolphinQualityControl()
    
    # Check available documents
    available_docs = []
    for json_file in qc.recognition_json_dir.glob("*.json"):
        doc_id = json_file.stem
        available_docs.append(doc_id)
    
    print(f"📄 Available documents: {available_docs}")
    
    for doc_id in available_docs:
        print(f"\n{'='*60}")
        try:
            # Run quality check
            passed = qc.run_quality_check(doc_id)
            
            # Generate detailed report
            report_path = f"./results/quality_reports/{doc_id}_quality_report.md"
            Path(report_path).parent.mkdir(exist_ok=True)
            qc.generate_detailed_report(doc_id, report_path)
            
        except Exception as e:
            print(f"❌ Error processing {doc_id}: {e}")


if __name__ == "__main__":
    main()