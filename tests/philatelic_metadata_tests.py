"""
Philatelic Metadata Tests and Verification Functions

This module contains functions to test and verify that chunks have been properly
enriched with philatelic metadata. Extracted from dolphin_parser.ipynb notebook.
"""

from typing import Dict, List, Any, Tuple, Optional
import json
from pathlib import Path


def show_philatelic_entities(ox_data: Dict[str, Any], max_examples: int = 10) -> List[Tuple[int, Dict[str, Any]]]:
    """
    Muestra chunks que tienen entidades filatélicas para verificar el enriquecimiento
    
    Args:
        ox_data: OXCART data structure with enriched chunks
        max_examples: Maximum number of examples to show
    
    Returns:
        List of tuples (chunk_index, chunk_data) for chunks with philatelic entities
    """
    
    chunks_with_entities = []
    
    for i, chunk in enumerate(ox_data.get('chunks', [])):
        entities = chunk.get('metadata', {}).get('entities', {})
        
        # Verificar si tiene alguna entidad filatélica
        has_entities = any([
            entities.get('catalog'),
            entities.get('dates'),
            entities.get('prices'),
            entities.get('values'),
            entities.get('colors'),
            entities.get('designs'),
            entities.get('varieties')
        ])
        
        if has_entities:
            chunks_with_entities.append((i, chunk))
    
    print(f"📊 Total chunks: {len(ox_data.get('chunks', []))}")
    print(f"🏷️ Chunks con entidades filatélicas: {len(chunks_with_entities)}")
    print(f"📈 Porcentaje enriquecido: {len(chunks_with_entities)/len(ox_data.get('chunks', []))*100:.1f}%")
    print("\n" + "="*80)
    
    # Mostrar ejemplos
    for idx, (chunk_idx, chunk) in enumerate(chunks_with_entities[:max_examples]):
        print(f"\n🔍 CHUNK #{chunk_idx} - Tipo: {chunk.get('chunk_type', 'unknown')}")
        print(f"📄 ID: {chunk.get('chunk_id', 'no-id')}")
        
        # Mostrar texto (primeros 150 caracteres)
        text = chunk.get('text', '')
        if len(text) > 150:
            text = text[:150] + "..."
        print(f"📝 Texto: {text}")
        
        # Mostrar entidades encontradas
        entities = chunk.get('metadata', {}).get('entities', {})
        
        if entities.get('catalog'):
            print(f"📖 Catálogos: {entities['catalog']}")
        
        if entities.get('dates'):
            print(f"📅 Fechas: {entities['dates']}")
        
        if entities.get('prices'):
            print(f"💰 Precios: {entities['prices']}")
        
        if entities.get('values'):
            print(f"💎 Valores postales: {entities['values']}")
        
        if entities.get('colors'):
            print(f"🎨 Colores: {entities['colors']}")
        
        if entities.get('designs'):
            print(f"🖼️ Diseños: {entities['designs']}")
        
        if entities.get('varieties'):
            print(f"🔄 Variedades: {entities['varieties']}")
        
        # Mostrar topics si existen
        topics = chunk.get('metadata', {}).get('topics', {})
        if topics:
            print(f"🏷️ Topics: {topics}")
        
        print("-" * 60)
    
    if len(chunks_with_entities) > max_examples:
        print(f"\n... y {len(chunks_with_entities) - max_examples} chunks más con entidades filatélicas")
    
    return chunks_with_entities


def analyze_philatelic_entities(ox_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Análisis detallado de las entidades filatélicas encontradas
    
    Args:
        ox_data: OXCART data structure with enriched chunks
    
    Returns:
        Dictionary with analysis statistics
    """
    
    entity_stats = {
        'catalog': {'count': 0, 'systems': {}},
        'dates': {'count': 0, 'years': set()},
        'prices': {'count': 0, 'currencies': {}},
        'values': {'count': 0, 'units': {}},
        'colors': {'count': 0, 'unique_colors': set()},
        'designs': {'count': 0, 'unique_designs': set()},
        'varieties': {'count': 0, 'types': {}}
    }
    
    topic_stats = {}
    chunk_type_stats = {}
    
    for chunk in ox_data.get('chunks', []):
        chunk_type = chunk.get('chunk_type', 'unknown')
        chunk_type_stats[chunk_type] = chunk_type_stats.get(chunk_type, 0) + 1
        
        entities = chunk.get('metadata', {}).get('entities', {})
        
        # Catálogos
        if entities.get('catalog'):
            entity_stats['catalog']['count'] += 1
            for cat in entities['catalog']:
                system = cat.get('system', 'unknown')
                entity_stats['catalog']['systems'][system] = entity_stats['catalog']['systems'].get(system, 0) + 1
        
        # Fechas
        if entities.get('dates'):
            entity_stats['dates']['count'] += 1
            for date in entities['dates']:
                if len(date) >= 4:
                    year = date[:4]
                    if year.isdigit():
                        entity_stats['dates']['years'].add(year)
        
        # Precios
        if entities.get('prices'):
            entity_stats['prices']['count'] += 1
            for price in entities['prices']:
                currency = price.get('currency', 'unknown')
                entity_stats['prices']['currencies'][currency] = entity_stats['prices']['currencies'].get(currency, 0) + 1
        
        # Valores postales
        if entities.get('values'):
            entity_stats['values']['count'] += 1
            for val in entities['values']:
                unit = val.get('unit', 'unknown')
                entity_stats['values']['units'][unit] = entity_stats['values']['units'].get(unit, 0) + 1
        
        # Colores
        if entities.get('colors'):
            entity_stats['colors']['count'] += 1
            entity_stats['colors']['unique_colors'].update(entities['colors'])
        
        # Diseños
        if entities.get('designs'):
            entity_stats['designs']['count'] += 1
            entity_stats['designs']['unique_designs'].update(entities['designs'])
        
        # Variedades
        if entities.get('varieties'):
            entity_stats['varieties']['count'] += 1
            for variety in entities['varieties']:
                v_class = variety.get('class', 'unknown')
                entity_stats['varieties']['types'][v_class] = entity_stats['varieties']['types'].get(v_class, 0) + 1
        
        # Topics
        topics = chunk.get('metadata', {}).get('topics', {})
        if topics.get('primary'):
            topic_stats[topics['primary']] = topic_stats.get(topics['primary'], 0) + 1
    
    print("🔍 ANÁLISIS DETALLADO DE ENTIDADES FILATÉLICAS")
    print("=" * 60)
    
    print(f"📖 Catálogos encontrados en {entity_stats['catalog']['count']} chunks:")
    for system, count in entity_stats['catalog']['systems'].items():
        print(f"   - {system}: {count}")
    
    print(f"\n📅 Fechas encontradas en {entity_stats['dates']['count']} chunks:")
    years_sorted = sorted(entity_stats['dates']['years'])
    if len(years_sorted) > 10:
        print(f"   - Años: {years_sorted[:5]}...{years_sorted[-5:]} ({len(years_sorted)} años únicos)")
    else:
        print(f"   - Años: {years_sorted}")
    
    print(f"\n💰 Precios encontrados en {entity_stats['prices']['count']} chunks:")
    for currency, count in entity_stats['prices']['currencies'].items():
        print(f"   - {currency}: {count}")
    
    print(f"\n💎 Valores postales encontrados en {entity_stats['values']['count']} chunks:")
    for unit, count in entity_stats['values']['units'].items():
        print(f"   - {unit}: {count}")
    
    print(f"\n🎨 Colores encontrados en {entity_stats['colors']['count']} chunks:")
    colors_list = sorted(list(entity_stats['colors']['unique_colors']))[:10]
    print(f"   - {colors_list}")
    
    print(f"\n🖼️ Diseños encontrados en {entity_stats['designs']['count']} chunks:")
    designs_list = sorted(list(entity_stats['designs']['unique_designs']))
    print(f"   - {designs_list}")
    
    print(f"\n🔄 Variedades encontradas en {entity_stats['varieties']['count']} chunks:")
    for v_type, count in entity_stats['varieties']['types'].items():
        print(f"   - {v_type}: {count}")
    
    print(f"\n🏷️ Topics principales más frecuentes:")
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    for topic, count in sorted_topics:
        print(f"   - {topic}: {count}")
    
    print(f"\n📄 Distribución de tipos de chunks:")
    sorted_types = sorted(chunk_type_stats.items(), key=lambda x: x[1], reverse=True)
    for chunk_type, count in sorted_types:
        print(f"   - {chunk_type}: {count}")
    
    # Convert sets to lists for JSON serialization
    entity_stats['dates']['years'] = list(entity_stats['dates']['years'])
    entity_stats['colors']['unique_colors'] = list(entity_stats['colors']['unique_colors'])
    entity_stats['designs']['unique_designs'] = list(entity_stats['designs']['unique_designs'])
    
    return {
        'entity_stats': entity_stats,
        'topic_stats': topic_stats,
        'chunk_type_stats': chunk_type_stats
    }


def show_catalog_examples_by_system(ox_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Muestra ejemplos específicos de cada sistema de catálogo encontrado
    
    Args:
        ox_data: OXCART data structure with enriched chunks
    
    Returns:
        Dictionary with catalog examples by system
    """
    
    catalog_examples = {}
    
    # Recopilar ejemplos por sistema de catálogo
    for i, chunk in enumerate(ox_data.get('chunks', [])):
        entities = chunk.get('metadata', {}).get('entities', {})
        
        if entities.get('catalog'):
            for cat_entry in entities['catalog']:
                system = cat_entry.get('system', 'unknown')
                
                if system not in catalog_examples:
                    catalog_examples[system] = []
                
                # Limitar a máximo 3 ejemplos por sistema
                if len(catalog_examples[system]) < 3:
                    catalog_examples[system].append({
                        'chunk_index': i,
                        'chunk_id': chunk.get('chunk_id', 'no-id'),
                        'catalog_entry': cat_entry,
                        'text_sample': chunk.get('text', '')[:200] + "..." if len(chunk.get('text', '')) > 200 else chunk.get('text', ''),
                        'chunk_type': chunk.get('chunk_type', 'unknown')
                    })
    
    print("📖 EJEMPLOS DE CATÁLOGOS POR SISTEMA")
    print("=" * 80)
    
    if not catalog_examples:
        print("❌ No se encontraron catálogos en los chunks")
        return {}
    
    for system, examples in catalog_examples.items():
        print(f"\n🏷️ SISTEMA: {system.upper()}")
        print(f"📊 Total encontrados: {len(examples)} ejemplos")
        print("-" * 50)
        
        for idx, example in enumerate(examples, 1):
            print(f"\n   📌 Ejemplo #{idx}:")
            print(f"   📄 Chunk ID: {example['chunk_id']}")
            print(f"   📝 Tipo: {example['chunk_type']}")
            print(f"   🔢 Número de catálogo: {example['catalog_entry'].get('number', 'N/A')}")
            print(f"   📖 Sistema: {example['catalog_entry'].get('system', 'N/A')}")
            print(f"   📋 Texto muestra:")
            print(f"      \"{example['text_sample']}\"")
            print("   " + "-" * 40)
    
    # Resumen final
    print(f"\n📊 RESUMEN:")
    total_systems = len(catalog_examples)
    total_examples = sum(len(examples) for examples in catalog_examples.values())
    print(f"   • Sistemas de catálogo únicos: {total_systems}")
    print(f"   • Total de ejemplos mostrados: {total_examples}")
    
    return catalog_examples


def verify_enrichment_completeness(ox_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifica la completitud del enriquecimiento filatélico
    
    Args:
        ox_data: OXCART data structure with enriched chunks
    
    Returns:
        Dictionary with verification results
    """
    
    total_chunks = len(ox_data.get('chunks', []))
    enriched_chunks = 0
    missing_enrichment = []
    
    entity_coverage = {
        'catalog': 0,
        'dates': 0,
        'prices': 0,
        'values': 0,
        'colors': 0,
        'designs': 0,
        'varieties': 0,
        'topics': 0
    }
    
    for i, chunk in enumerate(ox_data.get('chunks', [])):
        entities = chunk.get('metadata', {}).get('entities', {})
        topics = chunk.get('metadata', {}).get('topics', {})
        
        has_entities = False
        
        # Check each type of entity
        for entity_type in entity_coverage.keys():
            if entity_type == 'topics':
                if topics:
                    entity_coverage[entity_type] += 1
                    has_entities = True
            elif entities.get(entity_type):
                entity_coverage[entity_type] += 1
                has_entities = True
        
        if has_entities:
            enriched_chunks += 1
        else:
            missing_enrichment.append({
                'chunk_index': i,
                'chunk_id': chunk.get('chunk_id', 'no-id'),
                'chunk_type': chunk.get('chunk_type', 'unknown'),
                'text_sample': chunk.get('text', '')[:100] + "..." if len(chunk.get('text', '')) > 100 else chunk.get('text', '')
            })
    
    enrichment_percentage = (enriched_chunks / total_chunks * 100) if total_chunks > 0 else 0
    
    verification_results = {
        'total_chunks': total_chunks,
        'enriched_chunks': enriched_chunks,
        'enrichment_percentage': round(enrichment_percentage, 2),
        'entity_coverage': entity_coverage,
        'missing_enrichment_samples': missing_enrichment[:5],  # First 5 examples
        'missing_enrichment_count': len(missing_enrichment)
    }
    
    print("✅ VERIFICACIÓN DE COMPLETITUD DEL ENRIQUECIMIENTO")
    print("=" * 60)
    print(f"📊 Total de chunks: {total_chunks}")
    print(f"🏷️ Chunks enriquecidos: {enriched_chunks}")
    print(f"📈 Porcentaje de enriquecimiento: {enrichment_percentage:.1f}%")
    print(f"❌ Chunks sin enriquecimiento: {len(missing_enrichment)}")
    
    print(f"\n📋 Cobertura por tipo de entidad:")
    for entity_type, count in entity_coverage.items():
        percentage = (count / total_chunks * 100) if total_chunks > 0 else 0
        print(f"   - {entity_type}: {count} chunks ({percentage:.1f}%)")
    
    if missing_enrichment:
        print(f"\n🔍 Ejemplos de chunks sin enriquecimiento:")
        for i, missing in enumerate(missing_enrichment[:3], 1):
            print(f"   {i}. [{missing['chunk_type']}] {missing['text_sample']}")
    
    return verification_results


def save_analysis_report(analysis_data: Dict[str, Any], filepath: str) -> str:
    """
    Save analysis results to a JSON file
    
    Args:
        analysis_data: Analysis results dictionary
        filepath: Output file path
    
    Returns:
        Path to saved file
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)
    return filepath


def run_full_analysis(ox_data: Dict[str, Any], output_dir: str = "./results/analysis") -> Dict[str, Any]:
    """
    Run complete analysis of philatelic enrichment
    
    Args:
        ox_data: OXCART data structure with enriched chunks
        output_dir: Directory to save analysis results
    
    Returns:
        Complete analysis results
    """
    
    print("🚀 INICIANDO ANÁLISIS COMPLETO DE ENRIQUECIMIENTO FILATÉLICO")
    print("=" * 80)
    
    # Run all analyses
    philatelic_chunks = show_philatelic_entities(ox_data, max_examples=5)
    entity_analysis = analyze_philatelic_entities(ox_data)
    catalog_examples = show_catalog_examples_by_system(ox_data)
    verification_results = verify_enrichment_completeness(ox_data)
    
    # Compile complete results
    complete_analysis = {
        'summary': {
            'total_chunks': len(ox_data.get('chunks', [])),
            'enriched_chunks': len(philatelic_chunks),
            'enrichment_percentage': verification_results['enrichment_percentage']
        },
        'entity_analysis': entity_analysis,
        'catalog_examples': catalog_examples,
        'verification_results': verification_results,
        'philatelic_chunks_sample': [
            {
                'chunk_index': idx,
                'chunk_id': chunk.get('chunk_id'),
                'chunk_type': chunk.get('chunk_type'),
                'entities': chunk.get('metadata', {}).get('entities', {}),
                'topics': chunk.get('metadata', {}).get('topics', {})
            }
            for idx, chunk in philatelic_chunks[:10]
        ]
    }
    
    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    analysis_file = save_analysis_report(complete_analysis, str(output_path / "philatelic_analysis.json"))
    
    print(f"\n💾 Análisis guardado en: {analysis_file}")
    print("✅ Análisis completo finalizado")
    
    return complete_analysis