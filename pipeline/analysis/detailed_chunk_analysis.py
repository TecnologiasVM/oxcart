#!/usr/bin/env python3
"""
Análisis detallado de chunks para identificar pérdida de contexto
"""

import os
import json
import re

def analyze_context_loss(json_file):
    """Analiza casos específicos donde se pierde contexto"""
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    
    print("=== ANÁLISIS DETALLADO DE PÉRDIDA DE CONTEXTO ===\n")
    
    # Buscar secuencias SEC -> PARA consecutivas
    context_loss_cases = []
    
    for i in range(len(chunks) - 1):
        current_chunk = chunks[i]
        next_chunk = chunks[i + 1]
        
        current_labels = current_chunk.get('metadata', {}).get('labels', [])
        next_labels = next_chunk.get('metadata', {}).get('labels', [])
        
        if 'sec' in current_labels and 'para' in next_labels:
            current_text = current_chunk.get('text', '').strip()
            next_text = next_chunk.get('text', '').strip()
            next_word_count = len(next_text.split())
            
            current_reading_order = current_chunk.get('metadata', {}).get('reading_order_range', [])
            next_reading_order = next_chunk.get('metadata', {}).get('reading_order_range', [])
            
            context_loss_cases.append({
                'sec_idx': i,
                'para_idx': i + 1,
                'sec_text': current_text,
                'para_text': next_text,
                'para_words': next_word_count,
                'sec_reading_order': current_reading_order,
                'para_reading_order': next_reading_order,
                'consecutive': True
            })
    
    print(f"Casos de SEC -> PARA consecutivos encontrados: {len(context_loss_cases)}\n")
    
    # Mostrar casos más problemáticos (headers seguidos de párrafos muy cortos)
    problematic = [case for case in context_loss_cases if case['para_words'] < 30]
    
    print(f"=== CASOS MÁS PROBLEMÁTICOS (SEC -> PARA < 30 palabras) ===")
    print(f"Cantidad: {len(problematic)}\n")
    
    for i, case in enumerate(problematic[:8]):
        print(f"CASO {i+1}:")
        print(f"  [SEC] chunk {case['sec_idx']} (reading order: {case['sec_reading_order']}):")
        print(f"     '{case['sec_text']}'")
        print(f"  [PARA] chunk {case['para_idx']} (reading order: {case['para_reading_order']}, {case['para_words']} palabras):")
        print(f"     '{case['para_text'][:150]}{'...' if len(case['para_text']) > 150 else ''}'")
        print(f"  [PROBLEMA] El header '{case['sec_text']}' está separado del contenido que le sigue")
        print(f"  [RECOMENDACION] Combinar en un solo chunk para mantener el contexto\n")
    
    # Buscar patrones específicos de pérdida de contexto
    print("=== ANÁLISIS DE PATRONES ESPECÍFICOS ===\n")
    
    # Buscar títulos de sección seguidos de contenido breve
    section_patterns = []
    for case in context_loss_cases:
        sec_text = case['sec_text'].upper()
        
        # Patrones típicos de secciones
        if any(pattern in sec_text for pattern in [
            'MEMBERSHIP', 'DUES', 'PUBLICATIONS', 'CONTENTS', 'NEWS', 
            'CATALOG', 'INDEX', 'SOCIETY', 'RECAPITULATION'
        ]):
            section_patterns.append(case)
    
    print(f"Secciones con patrones típicos: {len(section_patterns)}")
    
    for i, case in enumerate(section_patterns[:5]):
        print(f"\nPATRÓN {i+1}:")
        print(f"  [SECCION]: '{case['sec_text']}'")
        print(f"  [CONTENIDO] ({case['para_words']} palabras): '{case['para_text'][:100]}{'...' if len(case['para_text']) > 100 else ''}'")
    
    # Buscar casos donde el párrafo es demasiado corto para ser independiente
    very_short = [case for case in context_loss_cases if case['para_words'] < 10]
    
    print(f"\n=== CASOS EXTREMOS (< 10 palabras) ===")
    print(f"Cantidad: {len(very_short)}\n")
    
    for i, case in enumerate(very_short):
        print(f"EXTREMO {i+1}:")
        print(f"  [SEC]: '{case['sec_text']}'")
        print(f"  [PARA] ({case['para_words']} palabras): '{case['para_text']}'")
        print(f"  [NOTA] Este párrafo es demasiado corto para tener sentido independiente\n")
    
    return {
        'total_consecutive': len(context_loss_cases),
        'problematic': len(problematic),
        'very_short': len(very_short),
        'section_patterns': len(section_patterns)
    }

def show_chunk_sequences(json_file):
    """Muestra secuencias de chunks para entender el flujo"""
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    
    print("\n=== SECUENCIAS DE CHUNKS PARA CONTEXTO ===\n")
    
    # Mostrar algunas secuencias de 3-4 chunks para ver el flujo
    for start_idx in [0, 20, 50, 100]:
        if start_idx + 3 < len(chunks):
            print(f"Secuencia desde chunk {start_idx}:")
            
            for i in range(start_idx, min(start_idx + 4, len(chunks))):
                chunk = chunks[i]
                labels = chunk.get('metadata', {}).get('labels', [])
                text = chunk.get('text', '').strip()[:80]
                reading_order = chunk.get('metadata', {}).get('reading_order_range', [])
                word_count = len(chunk.get('text', '').split())
                
                label_str = ', '.join(labels) if labels else 'sin_label'
                print(f"  [{i:3d}] {label_str:10s} (order: {reading_order}, {word_count:3d} palabras): {text}...")
            print()

if __name__ == "__main__":
    json_file = os.path.join("results", "parsed_jsons", "OXCART75_philatelic.json")  # relative to the repo root
    
    results = analyze_context_loss(json_file)
    show_chunk_sequences(json_file)
    
    print("\n=== RESUMEN DE RECOMENDACIONES ===")
    print(f"[OK] Total de casos SEC -> PARA consecutivos: {results['total_consecutive']}")
    print(f"[ATENCION] Casos problemáticos (< 30 palabras): {results['problematic']}")
    print(f"[CRITICO] Casos extremos (< 10 palabras): {results['very_short']}")
    print(f"[INFO] Patrones de sección identificados: {results['section_patterns']}")
    
    print(f"\n[RECOMENDACIONES]:")
    print(f"1. Combinar {results['very_short']} casos extremos automáticamente")
    print(f"2. Revisar manualmente {results['problematic']} casos problemáticos")
    print(f"3. Implementar regla: SEC + PARA_corto (< 30 palabras) = chunk_combinado")
    print(f"4. Mantener contexto semántico para mejor indexación en Weaviate")