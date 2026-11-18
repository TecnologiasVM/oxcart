#!/usr/bin/env python3
"""
Análisis simple de chunks philatelic para evitar problemas de codificación
"""

import json
import re
import sys

def safe_print(text):
    """Print text safely avoiding encoding issues"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace problematic characters
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(safe_text)

def analyze_chunks_simple(json_file):
    """Análisis simple evitando problemas de codificación"""
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data['chunks']
    
    safe_print("=== ANÁLISIS DE CHUNKS PHILATELIC ===")
    safe_print(f"Total de chunks: {len(chunks)}")
    
    # Contar por labels
    para_chunks = []
    sec_chunks = []
    
    for i, chunk in enumerate(chunks):
        labels = chunk.get('metadata', {}).get('labels', [])
        if 'para' in labels:
            para_chunks.append((i, chunk))
        elif 'sec' in labels:
            sec_chunks.append((i, chunk))
    
    safe_print(f"Chunks 'para': {len(para_chunks)}")
    safe_print(f"Chunks 'sec': {len(sec_chunks)}")
    
    # Analizar chunks para cortos
    short_para = []
    for i, chunk in para_chunks:
        text = chunk.get('text', '')
        word_count = len(text.split())
        if word_count < 50:
            short_para.append((i, chunk, word_count))
    
    safe_print(f"Chunks 'para' cortos (< 50 palabras): {len(short_para)} ({len(short_para)/len(para_chunks)*100:.1f}%)")
    
    # Buscar casos SEC -> PARA consecutivos
    consecutive_cases = []
    for i in range(len(chunks) - 1):
        current_labels = chunks[i].get('metadata', {}).get('labels', [])
        next_labels = chunks[i + 1].get('metadata', {}).get('labels', [])
        
        if 'sec' in current_labels and 'para' in next_labels:
            next_text = chunks[i + 1].get('text', '')
            next_words = len(next_text.split())
            
            consecutive_cases.append({
                'sec_idx': i,
                'para_idx': i + 1,
                'para_words': next_words,
                'sec_text': chunks[i].get('text', '')[:50],
                'para_text': next_text[:50]
            })
    
    safe_print(f"Casos SEC -> PARA consecutivos: {len(consecutive_cases)}")
    
    # Casos problemáticos (párrafos muy cortos después de sección)
    problematic = [case for case in consecutive_cases if case['para_words'] < 30]
    safe_print(f"Casos problemáticos (< 30 palabras): {len(problematic)}")
    
    very_short = [case for case in consecutive_cases if case['para_words'] < 10]
    safe_print(f"Casos extremos (< 10 palabras): {len(very_short)}")
    
    safe_print("\n=== EJEMPLOS DE CASOS PROBLEMÁTICOS ===")
    
    for i, case in enumerate(problematic[:5]):
        safe_print(f"\nCASO {i+1}:")
        safe_print(f"  SEC (chunk {case['sec_idx']}): {case['sec_text'].replace(chr(10), ' ').replace(chr(13), ' ')}")
        safe_print(f"  PARA (chunk {case['para_idx']}, {case['para_words']} palabras): {case['para_text'].replace(chr(10), ' ').replace(chr(13), ' ')}")
        safe_print(f"  PROBLEMA: Header separado de contenido breve")
    
    safe_print("\n=== CASOS EXTREMOS ===")
    
    for i, case in enumerate(very_short):
        safe_print(f"\nEXTREMO {i+1}:")
        safe_print(f"  SEC: {case['sec_text'].replace(chr(10), ' ').replace(chr(13), ' ')}")
        safe_print(f"  PARA ({case['para_words']} palabras): {case['para_text'].replace(chr(10), ' ').replace(chr(13), ' ')}")
    
    # Distribución de longitudes
    para_lengths = [len(chunk[1].get('text', '').split()) for chunk in para_chunks]
    para_lengths.sort()
    
    safe_print(f"\n=== ESTADÍSTICAS DE LONGITUD (palabras) ===")
    safe_print(f"Mínimo: {min(para_lengths)}")
    safe_print(f"Máximo: {max(para_lengths)}")
    safe_print(f"Promedio: {sum(para_lengths)/len(para_lengths):.1f}")
    safe_print(f"Mediana: {para_lengths[len(para_lengths)//2]}")
    
    # Percentiles
    safe_print(f"Percentil 25: {para_lengths[len(para_lengths)//4]}")
    safe_print(f"Percentil 75: {para_lengths[3*len(para_lengths)//4]}")
    
    safe_print(f"\n=== RECOMENDACIONES ===")
    safe_print(f"1. Combinar {len(very_short)} casos extremos automáticamente")
    safe_print(f"2. Revisar {len(problematic)} casos problemáticos manualmente")
    safe_print(f"3. Regla sugerida: SEC + PARA(<30 palabras) = chunk combinado")
    safe_print(f"4. Esto mejorará el contexto semántico para Weaviate")
    
    return {
        'total_chunks': len(chunks),
        'para_chunks': len(para_chunks),
        'sec_chunks': len(sec_chunks),
        'short_para': len(short_para),
        'consecutive_cases': len(consecutive_cases),
        'problematic': len(problematic),
        'very_short': len(very_short)
    }

if __name__ == "__main__":
    json_file = r"C:\Users\USER\Desktop\Oxcart RAG\results\parsed_jsons\OXCART75_philatelic.json"
    results = analyze_chunks_simple(json_file)