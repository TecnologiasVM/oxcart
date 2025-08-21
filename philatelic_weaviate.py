
import weaviate
import weaviate.classes as wvc

# Configuración de Weaviate y OpenAI
WEAVIATE_URL = "http://localhost:8080"  # Cambiar según tu setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Asegurar que esté en tu .env

if not OPENAI_API_KEY:
    print("⚠️ ADVERTENCIA: OPENAI_API_KEY no encontrada en variables de entorno")
    print("💡 Para usar embeddings de OpenAI, configura tu API key:")

def create_weaviate_client(url: str = WEAVIATE_URL, openai_key: Optional[str] = None) -> weaviate.WeavateClient:
    """Crear cliente de Weaviate con autenticación OpenAI"""
    try:
        # Headers para OpenAI si se proporciona key
        headers = {}
        if openai_key:
            headers["X-OpenAI-Api-Key"] = openai_key
        
        client = weaviate.connect_to_local(
            host=url.replace("http://", "").replace("https://", ""),
            headers=headers
        )
        
        print(f"✅ Conectado a Weaviate en {url}")
        return client
    except Exception as e:
        print(f"❌ Error conectando a Weaviate: {e}")
        print(f"💡 Asegúrate que Weaviate esté corriendo en {url}")
        raise

def create_oxcart_collection(client: weaviate.WeavateClient, collection_name: str = "Oxcart") -> bool:
    """Crear la colección Oxcart con esquema optimizado para filatelia"""
    
    try:
        # Verificar si la colección ya existe
        if client.collections.exists(collection_name):
            print(f"⚠️ Colección '{collection_name}' ya existe")
            response = input("¿Deseas eliminarla y recrearla? (y/n): ")
            if response.lower() == 'y':
                client.collections.delete(collection_name)
                print(f"🗑️ Colección '{collection_name}' eliminada")
            else:
                print("ℹ️ Usando colección existente")
                return True

        # Crear colección con esquema completo
        collection = client.collections.create(
            name=collection_name,
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(
                model="text-embedding-3-large"
            ),
            properties=[
                # Propiedades principales
                wvc.config.Property(
                    name="chunk_id",
                    data_type=wvc.config.DataType.TEXT,
                    description="Identificador único del chunk"
                ),
                wvc.config.Property(
                    name="chunk_type", 
                    data_type=wvc.config.DataType.TEXT,
                    description="Tipo de contenido (text, table, figure, etc.)"
                ),
                wvc.config.Property(
                    name="text",
                    data_type=wvc.config.DataType.TEXT,
                    description="Contenido principal del chunk para vectorización"
                ),
                wvc.config.Property(
                    name="doc_id",
                    data_type=wvc.config.DataType.TEXT,
                    description="ID del documento origen"
                ),
                wvc.config.Property(
                    name="page_number",
                    data_type=wvc.config.DataType.INT,
                    description="Número de página en el documento"
                ),
                
                # Metadatos filatélicos específicos
                wvc.config.Property(
                    name="catalog_systems",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Sistemas de catálogo encontrados (Scott, M, A, etc.)"
                ),
                wvc.config.Property(
                    name="catalog_numbers",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Números de catálogo específicos"
                ),
                wvc.config.Property(
                    name="dates",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Fechas normalizadas encontradas"
                ),
                wvc.config.Property(
                    name="years",
                    data_type=wvc.config.DataType.INT_ARRAY,
                    description="Años extraídos para filtros numéricos"
                ),
                wvc.config.Property(
                    name="colors",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Colores detectados en el contenido"
                ),
                wvc.config.Property(
                    name="topics_primary",
                    data_type=wvc.config.DataType.TEXT,
                    description="Topic principal detectado"
                ),
                wvc.config.Property(
                    name="topics_secondary",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Topics secundarios"
                ),
                wvc.config.Property(
                    name="topics_tags",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Tags específicos del contenido"
                ),
                
                # Metadatos adicionales
                wvc.config.Property(
                    name="has_prices",
                    data_type=wvc.config.DataType.BOOL,
                    description="Indica si el chunk contiene información de precios"
                ),
                wvc.config.Property(
                    name="has_varieties",
                    data_type=wvc.config.DataType.BOOL,
                    description="Indica si contiene variedades filatélicas"
                ),
                wvc.config.Property(
                    name="has_catalog",
                    data_type=wvc.config.DataType.BOOL,
                    description="Indica si contiene referencias de catálogo"
                ),
                
                # Metadatos estructurados como JSON
                wvc.config.Property(
                    name="metadata_json",
                    data_type=wvc.config.DataType.TEXT,
                    description="Metadatos completos en formato JSON"
                ),
                wvc.config.Property(
                    name="grounding_json",
                    data_type=wvc.config.DataType.TEXT,
                    description="Información de grounding (página, coordenadas)"
                )
            ]
        )
        
        print(f"✅ Colección '{collection_name}' creada exitosamente")
        print(f"📊 Vectorizador: OpenAI text-embedding-3-large")
        print(f"🗂️ Propiedades: {len(collection.config.get().properties)} campos definidos")
        return True
        
    except Exception as e:
        print(f"❌ Error creando colección: {e}")
        return False

# Probar conexión y crear colección
print("🔧 Configurando Weaviate...")


def transform_chunk_to_weaviate(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Transformar un chunk OXCART a formato Weaviate"""
    
    # Extraer metadatos y entidades
    metadata = chunk.get("metadata", {})
    entities = metadata.get("entities", {})
    topics = metadata.get("topics", {})
    grounding = chunk.get("grounding", [])
    
    # Extraer página del chunk_id o grounding
    page_number = 1
    if grounding and len(grounding) > 0:
        page_number = grounding[0].get("page", 1)
    elif ":" in chunk.get("chunk_id", ""):
        try:
            page_part = chunk["chunk_id"].split(":")[1]
            page_number = int(page_part.lstrip("0") or "1")
        except (ValueError, IndexError):
            page_number = 1
    
    # Procesar catálogos
    catalogs = entities.get("catalog", [])
    catalog_systems = list(set([cat.get("system", "") for cat in catalogs if cat.get("system")]))
    catalog_numbers = [cat.get("number", "") for cat in catalogs if cat.get("number")]
    
    # Procesar fechas y años
    dates = entities.get("dates", [])
    years = []
    for date in dates:
        if len(date) >= 4 and date[:4].isdigit():
            years.append(int(date[:4]))
    years = sorted(list(set(years)))
    
    # Extraer colores
    colors = entities.get("colors", [])
    
    # Procesar topics
    topics_primary = topics.get("primary", "")
    topics_secondary = topics.get("secondary", [])
    topics_tags = topics.get("tags", [])
    
    # Flags booleanos para filtros rápidos
    has_catalog = bool(catalogs)
    has_prices = bool(entities.get("prices", []))
    has_varieties = bool(entities.get("varieties", []))
    
    # Preparar objeto para Weaviate
    weaviate_obj = {
        "chunk_id": chunk.get("chunk_id", ""),
        "chunk_type": chunk.get("chunk_type", "text"),
        "text": chunk.get("text", ""),
        "doc_id": chunk.get("doc_id", "unknown"),
        "page_number": page_number,
        
        # Metadatos filatélicos
        "catalog_systems": catalog_systems,
        "catalog_numbers": catalog_numbers,
        "dates": dates,
        "years": years,
        "colors": colors,
        "topics_primary": topics_primary,
        "topics_secondary": topics_secondary,
        "topics_tags": topics_tags,
        
        # Flags booleanos
        "has_catalog": has_catalog,
        "has_prices": has_prices,
        "has_varieties": has_varieties,
        
        # Metadatos completos como JSON
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "grounding_json": json.dumps(grounding, ensure_ascii=False)
    }
    
    return weaviate_obj

def batch_index_chunks(
    client: weaviate.WeavateClient, 
    chunks: List[Dict[str, Any]], 
    collection_name: str = "Oxcart",
    batch_size: int = 50
) -> Dict[str, Any]:
    """Indexar chunks en Weaviate por lotes"""
    
    collection = client.collections.get(collection_name)
    total_chunks = len(chunks)
    successful = 0
    errors = []
    
    print(f"🚀 Iniciando indexación de {total_chunks} chunks en lotes de {batch_size}")
    
    for i in range(0, total_chunks, batch_size):
        batch = chunks[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        
        print(f"📦 Procesando lote {batch_num}/{total_batches} ({len(batch)} chunks)...")
        
        try:
            # Transformar chunks a formato Weaviate
            weaviate_objects = [transform_chunk_to_weaviate(chunk) for chunk in batch]
            
            # Insertar lote
            response = collection.data.insert_many(weaviate_objects)
            
            # Contar exitosos y errores
            batch_successful = sum(1 for obj in response.objects if obj.uuid)
            batch_errors = [obj for obj in response.objects if not obj.uuid]
            
            successful += batch_successful
            errors.extend(batch_errors)
            
            print(f"   ✅ {batch_successful}/{len(batch)} chunks indexados exitosamente")
            
            if batch_errors:
                print(f"   ⚠️ {len(batch_errors)} errores en este lote")
                for error in batch_errors[:3]:  # Mostrar solo los primeros 3 errores
                    print(f"      - Error: {error.errors}")
            
        except Exception as e:
            print(f"   ❌ Error en lote {batch_num}: {e}")
            errors.append({"batch": batch_num, "error": str(e)})
    
    # Resumen final
    print(f"\\n📊 RESUMEN DE INDEXACIÓN:")
    print(f"   ✅ Chunks indexados exitosamente: {successful}/{total_chunks}")
    print(f"   ❌ Chunks con errores: {len(errors)}")
    print(f"   📈 Tasa de éxito: {(successful/total_chunks)*100:.1f}%")
    
    if errors:
        print(f"\\n🔍 Primeros errores:")
        for error in errors[:5]:
            print(f"   - {error}")
    
    return {
        "total_chunks": total_chunks,
        "successful": successful,
        "errors": errors,
        "success_rate": (successful/total_chunks) * 100
    }

print("🔧 Funciones de transformación y indexación listas")


def search_chunks_semantic(
    client: weaviate.WeavateClient,
    query: str,
    collection_name: str = "Oxcart",
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Búsqueda semántica en la colección de chunks"""
    
    collection = client.collections.get(collection_name)
    
    # Construir filtros si se proporcionan
    where_filter = None
    if filters:
        conditions = []
        
        # Filtro por tipo de chunk
        if filters.get("chunk_type"):
            conditions.append(
                wvc.query.Filter.by_property("chunk_type").equal(filters["chunk_type"])
            )
        
        # Filtro por sistema de catálogo
        if filters.get("catalog_system"):
            conditions.append(
                wvc.query.Filter.by_property("catalog_systems").contains_any([filters["catalog_system"]])
            )
        
        # Filtro por años
        if filters.get("year_range"):
            year_min, year_max = filters["year_range"]
            conditions.append(
                wvc.query.Filter.by_property("years").greater_or_equal(year_min) &
                wvc.query.Filter.by_property("years").less_or_equal(year_max)
            )
        
        # Filtro por color
        if filters.get("color"):
            conditions.append(
                wvc.query.Filter.by_property("colors").contains_any([filters["color"]])
            )
        
        # Filtro por topic
        if filters.get("topic"):
            conditions.append(
                wvc.query.Filter.by_property("topics_primary").equal(filters["topic"]) |
                wvc.query.Filter.by_property("topics_secondary").contains_any([filters["topic"]])
            )
        
        # Combinar condiciones con AND
        if conditions:
            where_filter = conditions[0]
            for condition in conditions[1:]:
                where_filter = where_filter & condition
    
    try:
        # Ejecutar búsqueda
        response = collection.query.near_text(
            query=query,
            limit=limit,
            where=where_filter,
            return_metadata=wvc.query.MetadataQuery(distance=True, score=True)
        )
        
        # Formatear resultados
        results = []
        for obj in response.objects:
            result = {
                "uuid": str(obj.uuid),
                "score": obj.metadata.score if obj.metadata else 0.0,
                "distance": obj.metadata.distance if obj.metadata else 1.0,
                "chunk_id": obj.properties.get("chunk_id", ""),
                "chunk_type": obj.properties.get("chunk_type", ""),
                "text": obj.properties.get("text", "")[:300] + "..." if len(obj.properties.get("text", "")) > 300 else obj.properties.get("text", ""),
                "doc_id": obj.properties.get("doc_id", ""),
                "page_number": obj.properties.get("page_number", 0),
                "catalog_systems": obj.properties.get("catalog_systems", []),
                "catalog_numbers": obj.properties.get("catalog_numbers", []),
                "years": obj.properties.get("years", []),
                "colors": obj.properties.get("colors", []),
                "topics_primary": obj.properties.get("topics_primary", ""),
                "has_catalog": obj.properties.get("has_catalog", False),
                "has_prices": obj.properties.get("has_prices", False)
            }
            results.append(result)
        
        return results
        
    except Exception as e:
        print(f"❌ Error en búsqueda semántica: {e}")
        return []

def search_philatelic_queries(client: weaviate.WeavateClient, collection_name: str = "Oxcart"):
    """Ejemplos de búsquedas filatélicas específicas"""
    
    queries = [
        {
            "name": "Stamps Scott catalog",
            "query": "Scott catalog numbers stamps Costa Rica",
            "filters": {"catalog_system": "Scott"}
        },
        {
            "name": "Overprints and surcharges", 
            "query": "overprint surcharge stamps varieties",
            "filters": {"topic": "overprint"}
        },
        {
            "name": "Colors and designs",
            "query": "red blue violet stamps colors",
            "filters": {"color": "red"}
        },
        {
            "name": "Historical dates 1960s",
            "query": "stamps issued historical dates",
            "filters": {"year_range": (1960, 1969)}
        },
        {
            "name": "Tables with catalog data",
            "query": "catalog numbers prices values",
            "filters": {"chunk_type": "table"}
        }
    ]
    
    print("🔍 EJEMPLOS DE BÚSQUEDAS FILATÉLICAS")
    print("=" * 60)
    
    for example in queries:
        print(f"\\n📝 {example['name']}")
        print(f"🔎 Query: '{example['query']}'")
        print(f"🎛️ Filtros: {example.get('filters', 'Ninguno')}")
        
        results = search_chunks_semantic(
            client, 
            example["query"], 
            collection_name, 
            limit=3,
            filters=example.get("filters")
        )
        
        print(f"📊 Resultados encontrados: {len(results)}")
        
        for i, result in enumerate(results, 1):
            print(f"\\n   🏷️ #{i} (Score: {result['score']:.3f})")
            print(f"   📄 Chunk: {result['chunk_id']}")
            print(f"   📋 Tipo: {result['chunk_type']}")
            if result['catalog_systems']:
                print(f"   📖 Catálogos: {result['catalog_systems']}")
            if result['years']:
                print(f"   📅 Años: {result['years']}")
            if result['colors']:
                print(f"   🎨 Colores: {result['colors']}")
            print(f"   📝 Texto: {result['text'][:150]}...")
        
        print("-" * 40)

print("🔧 Funciones de búsqueda semántica listas")


# EJECUTAR INDEXACIÓN COMPLETA
# ⚠️ IMPORTANTE: Ejecutar solo después de configurar OPENAI_API_KEY y tener Weaviate corriendo

def run_complete_indexing(
    chunks_data: Dict[str, Any], 
    weaviate_url: str = WEAVIATE_URL,
    openai_key: Optional[str] = OPENAI_API_KEY,
    collection_name: str = "Oxcart"
):
    """Ejecutar el proceso completo de indexación"""
    
    print("🚀 INICIANDO PROCESO COMPLETO DE INDEXACIÓN EN WEAVIATE")
    print("=" * 70)
    
    # Paso 1: Conectar a Weaviate
    print("\\n1️⃣ Conectando a Weaviate...")
    try:
        client = create_weaviate_client(weaviate_url, openai_key)
    except Exception as e:
        print(f"❌ No se pudo conectar a Weaviate: {e}")
        return None
    
    # Paso 2: Crear colección
    print("\\n2️⃣ Configurando colección...")
    success = create_oxcart_collection(client, collection_name)
    if not success:
        print("❌ No se pudo crear la colección")
        return None
    
    # Paso 3: Preparar chunks
    chunks = chunks_data.get("chunks", [])
    if not chunks:
        print("❌ No se encontraron chunks para indexar")
        return None
    
    print(f"📊 Chunks a indexar: {len(chunks)}")
    
    # Paso 4: Indexar
    print("\\n3️⃣ Iniciando indexación...")
    indexing_results = batch_index_chunks(client, chunks, collection_name)
    
    # Paso 5: Validar indexación
    print("\\n4️⃣ Validando indexación...")
    collection = client.collections.get(collection_name)
    total_objects = collection.aggregate.over_all(total_count=True).total_count
    
    print(f"✅ Total objetos en Weaviate: {total_objects}")
    print(f"📊 Coincide con chunks enviados: {'✅' if total_objects == indexing_results['successful'] else '❌'}")
    
    # Paso 6: Ejemplos de búsqueda
    if total_objects > 0:
        print("\\n5️⃣ Ejecutando búsquedas de prueba...")
        search_philatelic_queries(client, collection_name)
    
    print("\\n🎉 PROCESO DE INDEXACIÓN COMPLETADO")
    
    return {
        "client": client,
        "indexing_results": indexing_results,
        "total_objects": total_objects
    }

# Mostrar instrucciones
print("📋 INSTRUCCIONES DE USO:")
print("1. Asegúrate de tener Weaviate corriendo (docker-compose up -d)")
print("2. Configura tu OPENAI_API_KEY en variables de entorno")  
print("3. Ejecuta: run_complete_indexing(ox)")
print("\\n💡 Para ejecutar manualmente:")
print("   result = run_complete_indexing(ox)")
print("\\n⚠️ Nota: La indexación puede tomar varios minutos debido a los embeddings de OpenAI")