#!/usr/bin/env python3
"""
Análisis de chunks philatelic para identificar patrones problemáticos
"""

import os
import json
import re
from collections import defaultdict

def count_words(text):
    """Cuenta palabras en un texto"""
    if not text:
        return 0
    # Limpia texto de caracteres especiales y cuenta palabras
    clean_text = re.sub(r'[^\w\s]', ' ', text)
    words = clean_text.split()
    return len(words)

def analyze_philatelic_chunks(json_file):
    """Analiza el JSON de chunks philatelic"""
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    print(f"Total de chunks: {len(chunks)}")
    
    # Clasificar chunks por label
    para_chunks = []
    sec_chunks = []
    other_chunks = []
    
    for i, chunk in enumerate(chunks):
        labels = chunk.get('metadata', {}).get('labels', [])
        if 'para' in labels:
            para_chunks.append((i, chunk))
        elif 'sec' in labels:
            sec_chunks.append((i, chunk))
        else:
            other_chunks.append((i, chunk))
    
    print(f"\n=== ESTADÍSTICAS GENERALES ===")
    print(f"Chunks con label 'para': {len(para_chunks)}")
    print(f"Chunks con label 'sec': {len(sec_chunks)}")
    print(f"Chunks con otros labels: {len(other_chunks)}")
    
    # Analizar chunks "para" cortos
    short_para_chunks = []
    for idx, chunk in para_chunks:
        text = chunk.get('text', '')
        word_count = count_words(text)
        if word_count < 50:
            short_para_chunks.append((idx, chunk, word_count))
    
    print(f"\n=== CHUNKS 'PARA' CORTOS (< 50 palabras) ===")
    print(f"Cantidad: {len(short_para_chunks)} de {len(para_chunks)} ({len(short_para_chunks)/len(para_chunks)*100:.1f}%)")
    
    # Analizar relación sec -> para
    print(f"\n=== ANÁLISIS DE RELACIÓN SEC -> PARA ===")
    problematic_cases = []
    
    for sec_idx, sec_chunk in sec_chunks:
        sec_reading_order = sec_chunk.get('metadata', {}).get('reading_order_range', [])
        sec_text = sec_chunk.get('text', '').strip()
        
        # Buscar el siguiente chunk "para" más cercano
        next_para = None
        min_distance = float('inf')
        
        for para_idx, para_chunk in para_chunks:
            para_reading_order = para_chunk.get('metadata', {}).get('reading_order_range', [])
            
            if para_reading_order and sec_reading_order:
                # Calcular distancia en reading order
                para_start = para_reading_order[0] if para_reading_order else float('inf')
                sec_end = sec_reading_order[-1] if sec_reading_order else 0
                
                if para_start > sec_end:  # Para viene después de sec
                    distance = para_start - sec_end
                    if distance < min_distance:
                        min_distance = distance
                        next_para = (para_idx, para_chunk, distance)
        
        if next_para:
            para_idx, para_chunk, distance = next_para
            para_text = para_chunk.get('text', '').strip()
            para_words = count_words(para_text)
            
            # Identificar casos problemáticos
            if distance <= 3 and para_words < 50:  # Muy cerca y párrafo corto
                problematic_cases.append({
                    'sec_idx': sec_idx,
                    'sec_text': sec_text[:100] + "..." if len(sec_text) > 100 else sec_text,
                    'sec_reading_order': sec_reading_order,
                    'para_idx': para_idx,
                    'para_text': para_text[:200] + "..." if len(para_text) > 200 else para_text,
                    'para_reading_order': para_chunk.get('metadata', {}).get('reading_order_range', []),
                    'para_words': para_words,
                    'distance': distance
                })
    
    print(f"Casos problemáticos encontrados: {len(problematic_cases)}")
    
    # Mostrar ejemplos específicos
    print(f"\n=== EJEMPLOS DE CHUNKS 'PARA' CORTOS ===")
    for i, (idx, chunk, word_count) in enumerate(short_para_chunks[:10]):
        text = chunk.get('text', '').strip()
        reading_order = chunk.get('metadata', {}).get('reading_order_range', [])
        print(f"\nEjemplo {i+1}:")
        print(f"  Chunk index: {idx}")
        print(f"  Palabras: {word_count}")
        print(f"  Reading order: {reading_order}")
        print(f"  Texto: '{text}'")
    
    print(f"\n=== EJEMPLOS DE CASOS PROBLEMÁTICOS (SEC -> PARA CORTO) ===")
    for i, case in enumerate(problematic_cases[:5]):
        print(f"\nCaso {i+1}:")
        print(f"  SEC (idx {case['sec_idx']}, order {case['sec_reading_order']}): '{case['sec_text']}'")
        print(f"  PARA (idx {case['para_idx']}, order {case['para_reading_order']}, {case['para_words']} palabras, distancia {case['distance']}): '{case['para_text']}'")
        print(f"  >>> PROBLEMA: Header separado de párrafo corto que debería estar unido")
    
    # Analizar distribución de longitudes
    para_word_counts = [count_words(chunk.get('text', '')) for _, chunk in para_chunks]
    para_word_counts.sort()
    
    print(f"\n=== DISTRIBUCIÓN DE LONGITUDES DE CHUNKS 'PARA' ===")
    print(f"Mínimo: {min(para_word_counts)} palabras")
    print(f"Máximo: {max(para_word_counts)} palabras")
    print(f"Promedio: {sum(para_word_counts)/len(para_word_counts):.1f} palabras")
    print(f"Mediana: {para_word_counts[len(para_word_counts)//2]} palabras")
    
    # Percentiles
    print(f"Percentil 10: {para_word_counts[len(para_word_counts)//10]} palabras")
    print(f"Percentil 25: {para_word_counts[len(para_word_counts)//4]} palabras")
    print(f"Percentil 75: {para_word_counts[3*len(para_word_counts)//4]} palabras")
    
    return {
        'total_chunks': len(chunks),
        'para_chunks': len(para_chunks),
        'sec_chunks': len(sec_chunks),
        'short_para_chunks': len(short_para_chunks),
        'problematic_cases': len(problematic_cases),
        'examples': problematic_cases[:5]
    }

if __name__ == "__main__":
    json_file = os.path.join("results", "parsed_jsons", "OXCART75_philatelic.json")  # relative to the repo root
    results = analyze_philatelic_chunks(json_file)