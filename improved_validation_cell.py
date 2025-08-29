# Código mejorado para reemplazar la celda de validación en el notebook
# Este código maneja los límites de GroupByAggregate correctamente

# Validar indexación con manejo de límites mejorado
if client:
    print("🔍 VALIDANDO INDEXACIÓN...")
    
    # Obtener estadísticas actuales con límite mayor
    current_stats = get_collection_stats(client, COLLECTION_NAME, limit=1000)
    
    if current_stats:
        print(f"\n📊 ESTADÍSTICAS DE WEAVIATE:")
        print(f"   📦 Total chunks indexados: {current_stats.get('total_chunks', 0):,}")
        print(f"   📄 Documentos únicos: {current_stats.get('total_documents', 0)}")
        
        # Mostrar advertencias de límites si existen
        if current_stats.get('docs_limited'):
            print(f"   {current_stats.get('warning_docs', '')}")
            print(f"   💡 Para ver todos los documentos, aumenta el límite en get_collection_stats()")
        
        if current_stats.get('types_limited'):
            print(f"   {current_stats.get('warning_types', '')}")
        
        # Información del límite usado
        limit_info = f"   🎯 Límite usado: {current_stats.get('limit_used', 'N/A')}"
        if current_stats.get('docs_limited') or current_stats.get('types_limited'):
            limit_info += " ⚠️ (alcanzado)"
        else:
            limit_info += " ✅ (suficiente)"
        print(limit_info)
        
        # Mostrar documentos indexados (con nota sobre límite)
        if current_stats.get('documents'):
            docs_count = len(current_stats['documents'])
            truncated_note = " (primeros resultados)" if current_stats.get('docs_limited') else " (todos)"
            print(f"\n📋 DOCUMENTOS EN WEAVIATE{truncated_note}:")
            
            # Mostrar hasta 20 documentos en la consola para evitar spam
            items_to_show = list(current_stats['documents'].items())[:20]
            for doc_id, chunk_count in items_to_show:
                print(f"   • {doc_id}: {chunk_count:,} chunks")
            
            if len(current_stats['documents']) > 20:
                remaining = len(current_stats['documents']) - 20
                print(f"   ... y {remaining} documentos más")
        
        # Mostrar tipos de chunks
        if current_stats.get('chunk_types'):
            print(f"\n🏷️ TIPOS DE CHUNKS:")
            for chunk_type, count in current_stats['chunk_types'].items():
                print(f"   • {chunk_type}: {count:,}")
        
        # Comparar con archivos originales
        if 'discovered_files' in locals() and discovered_files:
            expected_chunks = sum(f["chunks_count"] for f in discovered_files)
            expected_docs = len(discovered_files)
            indexed_chunks = current_stats.get('total_chunks', 0)
            indexed_docs = current_stats.get('total_documents', 0)
            
            print(f"\n🔄 COMPARACIÓN:")
            print(f"   📥 Chunks esperados: {expected_chunks:,}")
            print(f"   📤 Chunks indexados: {indexed_chunks:,}")
            print(f"   📁 Documentos esperados: {expected_docs:,}")
            print(f"   📂 Documentos únicos encontrados: {indexed_docs:,}")
            
            # Análisis de cobertura de chunks
            if indexed_chunks == expected_chunks:
                print(f"   ✅ ¡Indexación completa al 100%!")
            elif indexed_chunks > expected_chunks:
                excess = indexed_chunks - expected_chunks
                coverage = (indexed_chunks / expected_chunks) * 100
                print(f"   📊 Cobertura: {coverage:.1f}% (con {excess:,} chunks adicionales)")
                print(f"   💡 Puede haber duplicados o chunks de versiones anteriores")
            elif indexed_chunks > 0:
                coverage = (indexed_chunks / expected_chunks) * 100
                print(f"   📊 Cobertura: {coverage:.1f}%")
                if coverage < 100:
                    missing = expected_chunks - indexed_chunks
                    print(f"   ⚠️ Faltan {missing:,} chunks")
            else:
                print(f"   ❌ No hay chunks indexados")
                
            # Análisis de cobertura de documentos
            if not current_stats.get('docs_limited'):
                if indexed_docs == expected_docs:
                    print(f"   ✅ Todos los documentos están representados")
                elif indexed_docs > expected_docs:
                    print(f"   ⚠️ Hay más documentos únicos que archivos ({indexed_docs} vs {expected_docs})")
                    print(f"       Puede haber documentos de indexaciones anteriores")
                else:
                    missing_docs = expected_docs - indexed_docs
                    print(f"   ⚠️ Faltan {missing_docs} documentos únicos")
            else:
                print(f"   ⚠️ No se puede comparar documentos (límite alcanzado)")
                print(f"   💡 Usa get_collection_stats(client, COLLECTION_NAME, limit=1500) para ver todos")
    else:
        print("❌ No se pudieron obtener estadísticas de Weaviate")
else:
    print("⚠️ Sin conexión a Weaviate para validación")