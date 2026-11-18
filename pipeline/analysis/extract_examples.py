#!/usr/bin/env python3
"""
Extraer ejemplos específicos de pérdida de contexto
"""

import os
import json

def extract_specific_examples(json_file):
    """Extrae ejemplos específicos con texto completo"""
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    
    print("=== EJEMPLOS ESPECÍFICOS DE PÉRDIDA DE CONTEXTO ===\n")
    
    # Casos específicos encontrados
    problem_cases = [
        (62, 63),  # MEMBERSHIP RECAPITULATION
        (87, 88),  # PLATE_VARIETIES -> (See Figure 1)
        (129, 130), # Plate varieties -> (See Figure 3)
        (150, 151), # THE FOUR REALES STAMPS -> COLOR
        (152, 153), # PLATE VARIETIES -> (See Figure 4)
    ]
    
    for i, (sec_idx, para_idx) in enumerate(problem_cases):
        if sec_idx < len(chunks) and para_idx < len(chunks):
            sec_chunk = chunks[sec_idx]
            para_chunk = chunks[para_idx]
            
            sec_text = sec_chunk.get('text', '').strip()
            para_text = para_chunk.get('text', '').strip()
            
            sec_reading_order = sec_chunk.get('metadata', {}).get('reading_order_range', [])
            para_reading_order = para_chunk.get('metadata', {}).get('reading_order_range', [])
            
            para_words = len(para_text.split())
            
            print(f"EJEMPLO {i+1}:")
            print(f"  HEADER (chunk {sec_idx}, order {sec_reading_order}):")
            # Clean text for safe printing
            safe_sec_text = sec_text.encode('ascii', 'replace').decode('ascii')
            print(f"    \"{safe_sec_text}\"")
            
            print(f"  PÁRRAFO (chunk {para_idx}, order {para_reading_order}, {para_words} palabras):")
            safe_para_text = para_text.encode('ascii', 'replace').decode('ascii')
            print(f"    \"{safe_para_text}\"")
            
            print(f"  PROBLEMA:")
            print(f"    - El header está separado del contenido que describe")
            print(f"    - Al indexar por separado en Weaviate, se pierde la relación semántica")
            print(f"    - Un usuario buscando información sobre '{safe_sec_text}' podría no encontrar el contenido relevante")
            
            print(f"  TEXTO COMBINADO SUGERIDO:")
            combined_text = f"{safe_sec_text} {safe_para_text}".strip()
            print(f"    \"{combined_text}\"")
            print()
    
    # Buscar más ejemplos de chunks para muy cortos
    print("=== CHUNKS 'PARA' EXTREMADAMENTE CORTOS ===\n")
    
    very_short_paras = []
    for i, chunk in enumerate(chunks):
        labels = chunk.get('metadata', {}).get('labels', [])
        if 'para' in labels:
            text = chunk.get('text', '').strip()
            words = len(text.split())
            if words <= 5:
                very_short_paras.append((i, chunk, words, text))
    
    print(f"Chunks 'para' con 5 palabras o menos: {len(very_short_paras)}")
    
    for i, (idx, chunk, words, text) in enumerate(very_short_paras[:10]):
        reading_order = chunk.get('metadata', {}).get('reading_order_range', [])
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(f"  {i+1}. Chunk {idx} (order {reading_order}, {words} palabras): \"{safe_text}\"")
    
    # Buscar secuencias de chunks relacionados
    print(f"\n=== SECUENCIAS DE CONTEXTO ===\n")
    
    # Mostrar algunas secuencias para entender el flujo
    interesting_sequences = [
        (62, 66),  # MEMBERSHIP area
        (87, 92),  # PLATE_VARIETIES area
        (150, 156), # THE FOUR REALES area
    ]
    
    for start_idx, end_idx in interesting_sequences:
        if start_idx < len(chunks) and end_idx < len(chunks):
            print(f"SECUENCIA {start_idx}-{end_idx}:")
            
            for i in range(start_idx, min(end_idx, len(chunks))):
                chunk = chunks[i]
                labels = chunk.get('metadata', {}).get('labels', [])
                text = chunk.get('text', '').strip()
                words = len(text.split())
                reading_order = chunk.get('metadata', {}).get('reading_order_range', [])
                
                label_str = ', '.join(labels) if labels else 'no_label'
                safe_text = text[:60].encode('ascii', 'replace').decode('ascii')
                
                print(f"  [{i:3d}] {label_str:10s} (order: {reading_order}, {words:3d} palabras): {safe_text}...")
            print()

if __name__ == "__main__":
    json_file = os.path.join("results", "parsed_jsons", "OXCART75_philatelic.json")  # relative to the repo root
    extract_specific_examples(json_file)