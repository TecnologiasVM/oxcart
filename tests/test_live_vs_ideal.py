"""
Test del Pipeline LIVE vs Modelo Ideal
========================================

Este script simula el procesamiento LIVE (create_live_philatelic_data) 
y compara el resultado con el modelo ideal.
"""

import json
import statistics
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict
import os, sys
# tests/ lives one level below the repo root; make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dolphin_transformer import transform_dolphin_to_oxcart_preserving_labels
from philatelic_patterns import enrich_all_chunks_advanced_philatelic
from PIL import Image
import os


def load_json_safe(file_path: str) -> Dict[str, Any]:
    """Cargar archivo JSON de forma segura."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR cargando {file_path}: {e}")
        return {}


def simulate_live_processing(original_data: Dict[str, Any], pdf_file: str) -> Dict[str, Any]:
    """Simular el procesamiento LIVE exactamente como en el notebook."""
    
    print("Simulando procesamiento LIVE...")
    
    # Función para obtener dimensiones de página (simular)
    def get_page_dimensions(page_num):
        # Usar dimensiones estándar para simulación
        return (612, 792)  # Dimensiones típicas de PDF
    
    try:
        # Paso 1: Aplicar transformación dolphin_to_oxcart
        print("  1. Aplicando transformacion dolphin_to_oxcart...")
        recognition_results = original_data['pages']
        
        live_data = transform_dolphin_to_oxcart_preserving_labels(
            recognition_results,
            doc_id=pdf_file,
            page_dims_provider=get_page_dimensions,
            para_max_chars=1500,  # MEJORADO: Aumentado de 1000
            target_avg_length=300,  # MEJORADO: Aumentado de 150
            max_chunk_length=1200,  # MEJORADO: Aumentado de 800
            table_row_block_size=None,
            optimize_for_rag=True  # Activar optimizaciones
        )
        
        print(f"     -> Generados {len(live_data.get('chunks', []))} chunks base")
        
        # Paso 2: Enriquecer con philatelic
        print("  2. Aplicando enriquecimiento philatelic...")
        live_data = enrich_all_chunks_advanced_philatelic(live_data)
        
        print(f"     -> Chunks finales: {len(live_data.get('chunks', []))}")
        
        return live_data
        
    except Exception as e:
        print(f"ERROR en procesamiento LIVE: {e}")
        return {}


def analyze_and_compare(live_data: Dict[str, Any], ideal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analizar y comparar datos LIVE vs IDEAL."""
    
    # Analizar LIVE
    live_chunks = live_data.get('chunks', [])
    live_analysis = {
        'total_chunks': len(live_chunks),
        'text_lengths': [len(c.get('text', '')) for c in live_chunks],
        'chunk_types': defaultdict(int),
        'bbox_count': 0
    }
    
    for chunk in live_chunks:
        chunk_type = chunk.get('chunk_type', 'unknown')
        live_analysis['chunk_types'][chunk_type] += 1
        
        # Verificar bbox
        grounding = chunk.get('grounding', [])
        if grounding and grounding[0].get('box'):
            live_analysis['bbox_count'] += 1
    
    # Analizar IDEAL
    ideal_chunks = ideal_data.get('chunks', [])
    ideal_analysis = {
        'total_chunks': len(ideal_chunks),
        'text_lengths': [len(c.get('text', '')) for c in ideal_chunks],
        'chunk_types': defaultdict(int),
        'bbox_count': 0
    }
    
    for chunk in ideal_chunks:
        chunk_type = chunk.get('chunk_type', 'unknown')
        ideal_analysis['chunk_types'][chunk_type] += 1
        
        # Verificar bbox
        grounding = chunk.get('grounding', [])
        if grounding and grounding[0].get('box'):
            ideal_analysis['bbox_count'] += 1
    
    # Calcular estadísticas
    live_stats = {
        'avg_length': statistics.mean(live_analysis['text_lengths']) if live_analysis['text_lengths'] else 0,
        'median_length': statistics.median(live_analysis['text_lengths']) if live_analysis['text_lengths'] else 0,
        'min_length': min(live_analysis['text_lengths']) if live_analysis['text_lengths'] else 0,
        'max_length': max(live_analysis['text_lengths']) if live_analysis['text_lengths'] else 0,
        'bbox_coverage': live_analysis['bbox_count'] / max(1, live_analysis['total_chunks'])
    }
    
    ideal_stats = {
        'avg_length': statistics.mean(ideal_analysis['text_lengths']) if ideal_analysis['text_lengths'] else 0,
        'median_length': statistics.median(ideal_analysis['text_lengths']) if ideal_analysis['text_lengths'] else 0,
        'min_length': min(ideal_analysis['text_lengths']) if ideal_analysis['text_lengths'] else 0,
        'max_length': max(ideal_analysis['text_lengths']) if ideal_analysis['text_lengths'] else 0,
        'bbox_coverage': ideal_analysis['bbox_count'] / max(1, ideal_analysis['total_chunks'])
    }
    
    # Comparar
    comparison = {
        'live_analysis': live_analysis,
        'ideal_analysis': ideal_analysis,
        'live_stats': live_stats,
        'ideal_stats': ideal_stats,
        'similarity_metrics': {}
    }
    
    # Métricas de similitud
    chunk_count_ratio = min(live_analysis['total_chunks'], ideal_analysis['total_chunks']) / max(live_analysis['total_chunks'], ideal_analysis['total_chunks'], 1)
    
    length_similarity = 1 - abs(live_stats['avg_length'] - ideal_stats['avg_length']) / max(live_stats['avg_length'], ideal_stats['avg_length'], 1)
    
    bbox_similarity = min(live_stats['bbox_coverage'], ideal_stats['bbox_coverage']) / max(live_stats['bbox_coverage'], ideal_stats['bbox_coverage'], 0.1)
    
    # Similitud de tipos
    live_types = set(live_analysis['chunk_types'].keys())
    ideal_types = set(ideal_analysis['chunk_types'].keys())
    type_overlap = len(live_types & ideal_types) / len(live_types | ideal_types) if (live_types | ideal_types) else 0
    
    overall_similarity = statistics.mean([chunk_count_ratio, length_similarity, bbox_similarity, type_overlap])
    
    comparison['similarity_metrics'] = {
        'chunk_count_ratio': chunk_count_ratio,
        'length_similarity': length_similarity,
        'bbox_similarity': bbox_similarity,
        'type_overlap': type_overlap,
        'overall_similarity': overall_similarity
    }
    
    return comparison


def print_comparison_report(comparison: Dict[str, Any]):
    """Imprimir reporte de comparación."""
    
    live = comparison['live_analysis']
    ideal = comparison['ideal_analysis']
    live_stats = comparison['live_stats']
    ideal_stats = comparison['ideal_stats']
    metrics = comparison['similarity_metrics']
    
    print("\nRESULTADOS COMPARATIVOS:")
    print("=" * 60)
    
    # Estadísticas básicas
    print("CONTEO DE CHUNKS:")
    print(f"  LIVE:  {live['total_chunks']} chunks")
    print(f"  IDEAL: {ideal['total_chunks']} chunks")
    print(f"  Ratio: {metrics['chunk_count_ratio']:.3f}")
    
    print("\nLONGITUD DE TEXTO:")
    print(f"  LIVE:  {live_stats['avg_length']:.1f} chars promedio ({live_stats['min_length']}-{live_stats['max_length']})")
    print(f"  IDEAL: {ideal_stats['avg_length']:.1f} chars promedio ({ideal_stats['min_length']}-{ideal_stats['max_length']})")
    print(f"  Similitud: {metrics['length_similarity']:.3f}")
    
    print("\nCOBERTURA DE BBOX:")
    print(f"  LIVE:  {live_stats['bbox_coverage']:.3f} ({live['bbox_count']}/{live['total_chunks']})")
    print(f"  IDEAL: {ideal_stats['bbox_coverage']:.3f} ({ideal['bbox_count']}/{ideal['total_chunks']})")
    print(f"  Similitud: {metrics['bbox_similarity']:.3f}")
    
    print("\nTIPOS DE CHUNKS:")
    print("  LIVE:")
    for chunk_type, count in sorted(live['chunk_types'].items()):
        print(f"    {chunk_type}: {count}")
    print("  IDEAL:")
    for chunk_type, count in sorted(ideal['chunk_types'].items()):
        print(f"    {chunk_type}: {count}")
    print(f"  Overlap de tipos: {metrics['type_overlap']:.3f}")
    
    # Evaluación final
    print(f"\nEVALUACION GENERAL:")
    print(f"  Score de similitud: {metrics['overall_similarity']:.3f}")
    
    if metrics['overall_similarity'] > 0.8:
        assessment = "EXCELENTE - Pipeline LIVE muy cercano al ideal"
    elif metrics['overall_similarity'] > 0.6:
        assessment = "BUENO - Pipeline LIVE se acerca al ideal"
    elif metrics['overall_similarity'] > 0.4:
        assessment = "REGULAR - Pipeline LIVE necesita mejoras"
    else:
        assessment = "DEFICIENTE - Pipeline LIVE requiere trabajo significativo"
    
    print(f"  {assessment}")
    
    # Recomendaciones específicas
    print(f"\nRECOMENDACIONES:")
    if metrics['chunk_count_ratio'] < 0.8:
        print(f"  * Ajustar agrupacion de chunks (ratio: {metrics['chunk_count_ratio']:.3f})")
    
    if metrics['length_similarity'] < 0.8:
        print(f"  * Optimizar longitud de chunks (similitud: {metrics['length_similarity']:.3f})")
    
    if metrics['bbox_similarity'] < 0.9:
        print(f"  * Mejorar generacion de bbox (similitud: {metrics['bbox_similarity']:.3f})")
    
    if metrics['type_overlap'] < 0.8:
        print(f"  * Alinear tipos de chunks (overlap: {metrics['type_overlap']:.3f})")
    
    if metrics['overall_similarity'] > 0.7:
        print(f"  * El pipeline LIVE esta funcionando bien!")


def main():
    """Función principal."""
    print("TEST: PIPELINE LIVE vs MODELO IDEAL")
    print("=" * 60)
    
    # Cargar archivos
    dolphin_path = "./results/recognition_json/OXCART22.json"
    ideal_path = "C:/Users/VM-SERVER/Downloads/OXCART22_ideal.json"
    
    if not Path(dolphin_path).exists() or not Path(ideal_path).exists():
        print("ERROR: Archivos no encontrados")
        return
    
    original_data = load_json_safe(dolphin_path)
    ideal_data = load_json_safe(ideal_path)
    
    if not original_data or not ideal_data:
        print("ERROR: No se pudieron cargar los archivos")
        return
    
    print("OK: Archivos cargados")
    
    # Simular procesamiento LIVE
    live_data = simulate_live_processing(original_data, "OXCART22")
    
    if not live_data:
        print("ERROR: Fallo el procesamiento LIVE")
        return
    
    print("OK: Procesamiento LIVE completado")
    
    # Comparar resultados
    comparison = analyze_and_compare(live_data, ideal_data)
    
    # Imprimir reporte
    print_comparison_report(comparison)
    
    # Guardar resultado LIVE para referencia
    output_path = "./results/live_test_output.json"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(live_data, f, ensure_ascii=False, indent=2)
        print(f"\nResultado LIVE guardado en: {output_path}")
    except Exception as e:
        print(f"Error guardando resultado: {e}")


if __name__ == "__main__":
    main()