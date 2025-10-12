#!/usr/bin/env python3
"""
Script para unir PDFs en la misma carpeta donde está este archivo .py
Solo usa pypdf y funciona automáticamente sin parámetros

Instalar: pip install pypdf
Uso: python merge_pdfs.py
"""

import os
import re
from pathlib import Path

try:
    from pypdf import PdfWriter, PdfReader
except ImportError:
    print("❌ ERROR: Se necesita pypdf")
    print("💡 Instalar con: pip install pypdf")
    exit(1)

def obtener_numero_orden(nombre):
    """Extrae el primer número del nombre para ordenar correctamente"""
    match = re.search(r'^(\d+)', nombre)
    return int(match.group(1)) if match else 999999

def main():
    # Usar la carpeta donde está este script
    carpeta_actual = Path(__file__).parent
    print(f"🔍 Buscando PDFs en: {carpeta_actual.absolute()}")
    
    # Buscar todos los PDFs que empiecen con número
    pdfs = [f for f in carpeta_actual.glob("*.pdf") 
            if re.match(r'^\d+', f.name)]
    
    if not pdfs:
        print("❌ No encontré PDFs que empiecen con número (ej: 1.pdf, 13-14.pdf)")
        print("💡 Pon este script en la carpeta con tus PDFs numerados")
        return
    
    # Ordenar numéricamente
    pdfs_ordenados = sorted(pdfs, key=lambda x: obtener_numero_orden(x.name))
    
    print(f"\n📋 Encontré {len(pdfs_ordenados)} PDFs:")
    for i, pdf in enumerate(pdfs_ordenados, 1):
        tamaño_mb = pdf.stat().st_size / (1024 * 1024)
        print(f"  {i}. {pdf.name} ({tamaño_mb:.1f} MB)")
    
    # Unir PDFs
    print(f"\n🔄 Uniendo PDFs...")
    writer = PdfWriter()
    total_paginas = 0
    
    for pdf in pdfs_ordenados:
        try:
            reader = PdfReader(str(pdf))
            paginas = len(reader.pages)
            
            for page in reader.pages:
                writer.add_page(page)
            
            total_paginas += paginas
            print(f"  ✅ {pdf.name}: {paginas} páginas")
            
        except Exception as e:
            print(f"  ❌ Error con {pdf.name}: {e}")
    
    # Guardar resultado
    archivo_salida = carpeta_actual / "PDFs_Unidos.pdf"
    
    try:
        with open(archivo_salida, 'wb') as output_file:
            writer.write(output_file)
        
        tamaño_final = archivo_salida.stat().st_size / (1024 * 1024)
        
        print(f"\n🎉 ¡Listo!")
        print(f"📄 Archivo creado: {archivo_salida.name}")
        print(f"📊 Total páginas: {total_paginas}")
        print(f"💾 Tamaño: {tamaño_final:.1f} MB")
        
    except Exception as e:
        print(f"❌ Error al guardar: {e}")

if __name__ == "__main__":
    main()