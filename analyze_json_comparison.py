"""
Análisis Comparativo de Archivos JSON - OXCART22
=================================================

Script para comparar:
1. Archivo base Dolphin: results/recognition_json/OXCART22.json
2. Archivo ideal: C:/Users/USER/Downloads/OXCART22_ideal.json

Objetivo: Evaluar si el procesamiento LIVE se acerca al modelo ideal.
"""

import json
import statistics
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict


def load_json_safe(file_path: str) -> Dict[str, Any]:
    """Cargar archivo JSON de forma segura."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR cargando {file_path}: {e}")
        return {}


def analyze_json_structure(data: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Analizar estructura básica de un archivo JSON."""
    analysis = {
        "label": label,
        "main_keys": list(data.keys()),
        "has_chunks": "chunks" in data,
        "has_pages": "pages" in data,
        "total_chunks": 0,
        "total_pages": 0,
        "chunk_fields": set(),
        "metadata_present": False
    }
    
    # Analizar chunks si existen
    if "chunks" in data:
        chunks = data["chunks"]
        analysis["total_chunks"] = len(chunks)
        
        # Analizar campos de chunks (usando los primeros 5)
        for chunk in chunks[:5]:
            analysis["chunk_fields"].update(chunk.keys())
    
    # Analizar páginas si existen
    if "pages" in data:
        pages = data["pages"]
        analysis["total_pages"] = len(pages)
        total_elements = sum(len(p.get("elements", [])) for p in pages)
        analysis["total_elements"] = total_elements
    
    # Verificar metadatos
    if "extraction_metadata" in data:
        analysis["metadata_present"] = True
        analysis["metadata_keys"] = list(data["extraction_metadata"].keys()) if data["extraction_metadata"] else []
    
    return analysis


def sample_chunks(data: Dict[str, Any], num_samples: int = 5) -> List[Dict[str, Any]]:
    """Extraer muestras de chunks para análisis."""
    if "chunks" not in data:
        return []
    
    chunks = data["chunks"][:num_samples]
    samples = []
    
    for i, chunk in enumerate(chunks):
        sample = {
            "index": i,
            "chunk_id": chunk.get("chunk_id", f"chunk_{i}"),
            "chunk_type": chunk.get("chunk_type", "unknown"),
            "text_length": len(chunk.get("text", "")),
            "text_preview": chunk.get("text", "")[:100] + ("..." if len(chunk.get("text", "")) > 100 else ""),
            "has_grounding": "grounding" in chunk,
            "has_bbox": False,
            "bbox_format": "none"
        }
        
        # Analizar grounding/bbox
        if "grounding" in chunk and chunk["grounding"]:
            grounding = chunk["grounding"][0]
            sample["has_grounding"] = True
            sample["page"] = grounding.get("page", "N/A")
            
            if "box" in grounding and grounding["box"]:
                sample["has_bbox"] = True
                bbox = grounding["box"]
                if isinstance(bbox, dict):
                    sample["bbox_format"] = "normalized_dict"
                    sample["bbox_sample"] = {k: round(v, 4) for k, v in bbox.items()}
                elif isinstance(bbox, list):
                    sample["bbox_format"] = "absolute_list"
                    sample["bbox_sample"] = bbox
        
        # Analizar metadatos específicos
        if "metadata" in chunk:
            metadata = chunk["metadata"]
            sample["metadata_keys"] = list(metadata.keys())
        
        samples.append(sample)
    
    return samples


def analyze_chunk_characteristics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Analizar características de chunks en detalle."""
    if "chunks" not in data:
        return {"error": "No chunks found"}
    
    chunks = data["chunks"]
    
    # Estadísticas de texto
    text_lengths = [len(chunk.get("text", "")) for chunk in chunks]
    
    # Tipos de chunks
    chunk_types = [chunk.get("chunk_type", "unknown") for chunk in chunks]
    type_counts = defaultdict(int)
    for ct in chunk_types:
        type_counts[ct] += 1
    
    # Análisis de bbox
    bbox_analysis = {
        "total_chunks": len(chunks),
        "chunks_with_grounding": 0,
        "chunks_with_bbox": 0,
        "bbox_formats": defaultdict(int)
    }
    
    for chunk in chunks:
        if "grounding" in chunk and chunk["grounding"]:
            bbox_analysis["chunks_with_grounding"] += 1
            grounding = chunk["grounding"][0]
            
            if "box" in grounding and grounding["box"]:
                bbox_analysis["chunks_with_bbox"] += 1
                bbox = grounding["box"]
                
                if isinstance(bbox, dict):
                    bbox_analysis["bbox_formats"]["normalized_dict"] += 1
                elif isinstance(bbox, list):
                    bbox_analysis["bbox_formats"]["absolute_list"] += 1
    
    return {
        "text_length_stats": {
            "count": len(text_lengths),
            "avg": round(statistics.mean(text_lengths), 1) if text_lengths else 0,
            "median": statistics.median(text_lengths) if text_lengths else 0,
            "min": min(text_lengths) if text_lengths else 0,
            "max": max(text_lengths) if text_lengths else 0,
            "std": round(statistics.stdev(text_lengths), 1) if len(text_lengths) > 1 else 0
        },
        "chunk_types": dict(type_counts),
        "bbox_analysis": bbox_analysis
    }


def compare_structures(dolphin_analysis: Dict, ideal_analysis: Dict) -> Dict[str, Any]:
    """Comparar estructuras de ambos archivos."""
    comparison = {
        "structure_similarity": {},
        "chunk_count_comparison": {},
        "field_comparison": {},
        "recommendations": []
    }
    
    # Comparar conteos
    dolphin_chunks = dolphin_analysis.get("total_elements", 0)  # Elementos Dolphin
    ideal_chunks = ideal_analysis.get("total_chunks", 0)  # Chunks ideales
    
    comparison["chunk_count_comparison"] = {
        "dolphin_elements": dolphin_chunks,
        "ideal_chunks": ideal_chunks,
        "ratio": round(ideal_chunks / dolphin_chunks, 2) if dolphin_chunks > 0 else 0
    }
    
    # Comparar campos de chunks
    dolphin_fields = dolphin_analysis.get("chunk_fields", set())
    ideal_fields = ideal_analysis.get("chunk_fields", set())
    
    comparison["field_comparison"] = {
        "dolphin_only": list(dolphin_fields - ideal_fields),
        "ideal_only": list(ideal_fields - dolphin_fields),
        "common_fields": list(dolphin_fields & ideal_fields),
        "field_coverage": round(len(dolphin_fields & ideal_fields) / len(ideal_fields), 2) if ideal_fields else 0
    }
    
    return comparison


def main():
    """Función principal de análisis."""
    print("ANALISIS COMPARATIVO OXCART22")
    print("=" * 60)
    
    # Rutas de archivos
    dolphin_path = "./results/recognition_json/OXCART22.json"
    ideal_path = "C:/Users/USER/Downloads/OXCART22_ideal.json"
    
    # Verificar existencia
    if not Path(dolphin_path).exists():
        print(f"❌ No encontrado: {dolphin_path}")
        return
    
    if not Path(ideal_path).exists():
        print(f"❌ No encontrado: {ideal_path}")
        return
    
    print("Cargando archivos...")
    
    # Cargar datos
    dolphin_data = load_json_safe(dolphin_path)
    ideal_data = load_json_safe(ideal_path)
    
    if not dolphin_data or not ideal_data:
        print("ERROR: Error cargando archivos")
        return
    
    print("OK: Archivos cargados exitosamente")
    
    # 1. ANÁLISIS ESTRUCTURAL
    print("\n1. ANALISIS ESTRUCTURAL")
    print("-" * 40)
    
    dolphin_structure = analyze_json_structure(dolphin_data, "Dolphin Base")
    ideal_structure = analyze_json_structure(ideal_data, "Ideal Model")
    
    print(f"{dolphin_structure['label']}:")
    print(f"   * Campos principales: {dolphin_structure['main_keys']}")
    print(f"   * Total paginas: {dolphin_structure.get('total_pages', 'N/A')}")
    print(f"   * Total elementos: {dolphin_structure.get('total_elements', 'N/A')}")
    print(f"   * Campos de chunks: {len(dolphin_structure['chunk_fields'])}")
    
    print(f"\n{ideal_structure['label']}:")
    print(f"   * Campos principales: {ideal_structure['main_keys']}")
    print(f"   * Total chunks: {ideal_structure['total_chunks']}")
    print(f"   * Campos de chunks: {len(ideal_structure['chunk_fields'])}")
    print(f"   * Metadatos: {'SI' if ideal_structure['metadata_present'] else 'NO'}")
    
    # 2. MUESTRAS DE CHUNKS
    print("\n2. MUESTRAS DE CHUNKS")
    print("-" * 40)
    
    ideal_samples = sample_chunks(ideal_data, 5)
    
    print("IDEAL - Primeros 5 chunks:")
    for sample in ideal_samples:
        bbox_info = f" | bbox: {sample['bbox_format']}" if sample['has_bbox'] else " | sin bbox"
        print(f"   {sample['index']+1}. [{sample['chunk_type']}] {sample['text_length']} chars{bbox_info}")
        print(f"      {sample['text_preview']}")
        if sample['has_bbox'] and 'bbox_sample' in sample:
            print(f"      BBOX: {sample['bbox_sample']}")
    
    # 3. CARACTERÍSTICAS DETALLADAS
    print("\n3. ANALISIS DE CARACTERISTICAS")
    print("-" * 40)
    
    ideal_chars = analyze_chunk_characteristics(ideal_data)
    
    print("MODELO IDEAL:")
    print(f"   * Total chunks: {ideal_chars['text_length_stats']['count']}")
    print(f"   * Longitud promedio: {ideal_chars['text_length_stats']['avg']} chars")
    print(f"   * Rango: {ideal_chars['text_length_stats']['min']} - {ideal_chars['text_length_stats']['max']} chars")
    print(f"   * Chunks con bbox: {ideal_chars['bbox_analysis']['chunks_with_bbox']}/{ideal_chars['bbox_analysis']['total_chunks']}")
    print(f"   * Tipos principales: {dict(list(ideal_chars['chunk_types'].items())[:5])}")
    
    # 4. COMPARACIÓN ESTRUCTURAL
    print("\n4. COMPARACION ESTRUCTURAL")
    print("-" * 40)
    
    comparison = compare_structures(dolphin_structure, ideal_structure)
    
    print(f"Conteo de elementos:")
    print(f"   * Dolphin elementos: {comparison['chunk_count_comparison']['dolphin_elements']}")
    print(f"   * Ideal chunks: {comparison['chunk_count_comparison']['ideal_chunks']}")
    print(f"   * Ratio (ideal/dolphin): {comparison['chunk_count_comparison']['ratio']}")
    
    print(f"\nCobertura de campos:")
    print(f"   * Campos comunes: {len(comparison['field_comparison']['common_fields'])}")
    print(f"   * Solo en ideal: {comparison['field_comparison']['ideal_only']}")
    print(f"   * Cobertura: {comparison['field_comparison']['field_coverage']*100:.1f}%")
    
    # 5. EVALUACIÓN FINAL
    print("\n5. EVALUACION DEL PIPELINE LIVE")
    print("-" * 40)
    
    # Calcular score de similitud
    similarity_factors = [
        comparison['field_comparison']['field_coverage'],  # Cobertura de campos
        min(1.0, comparison['chunk_count_comparison']['ratio']),  # Ratio de chunks
        1.0 if ideal_chars['bbox_analysis']['chunks_with_bbox'] > 0 else 0  # Presencia de bbox
    ]
    
    overall_score = statistics.mean(similarity_factors)
    
    print(f"SCORE DE SIMILITUD: {overall_score:.3f}")
    
    if overall_score > 0.8:
        assessment = "EXCELENTE - Muy cerca del ideal"
    elif overall_score > 0.6:
        assessment = "BUENO - Se acerca al ideal"
    elif overall_score > 0.4:
        assessment = "REGULAR - Necesita mejoras"
    else:
        assessment = "DEFICIENTE - Requiere trabajo significativo"
    
    print(f"EVALUACION: {assessment}")
    
    # 6. RECOMENDACIONES
    print(f"\n6. RECOMENDACIONES")
    print("-" * 40)
    
    recommendations = []
    
    if comparison['chunk_count_comparison']['ratio'] < 0.8:
        recommendations.append("* Mejorar agrupacion de chunks - ratio muy bajo")
    
    if ideal_chars['bbox_analysis']['chunks_with_bbox'] > 0:
        recommendations.append("* Asegurar generacion correcta de bbox normalizados")
    
    if comparison['field_comparison']['field_coverage'] < 0.9:
        recommendations.append("* Implementar campos faltantes del modelo ideal")
    
    if ideal_chars['text_length_stats']['avg'] > 200:
        recommendations.append("* Optimizar longitud de chunks para mejor RAG performance")
    
    if not recommendations:
        recommendations.append("* El pipeline LIVE esta bien alineado con el modelo ideal")
    
    for rec in recommendations:
        print(f"   {rec}")
    
    print("\n" + "=" * 60)
    print("ANALISIS COMPLETADO")


if __name__ == "__main__":
    main()