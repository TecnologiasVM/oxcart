"""
Enhanced Philatelic Weaviate Integration (v2.1)
OXCART RAG System - Philatelic Document Vectorization

Compatibilidad: weaviate-client >= 4.16  (API v4)
Última actualización: 2025-08-22
"""

import os
import json
import weaviate
import weaviate.classes as wvc
from typing import Dict, Any, Optional, List
import re

# --------------------------------------------
# Configuración
# --------------------------------------------
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8083")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("ADVERTENCIA: OPENAI_API_KEY no encontrada en variables de entorno")
    print("Para usar embeddings de OpenAI, configura tu API key en el archivo .env")
    print("   Ejemplo: OPENAI_API_KEY=sk-xxx...")

# --------------------------------------------
# Cliente
# --------------------------------------------
def create_weaviate_client(url: str = WEAVIATE_URL, openai_key: Optional[str] = None) -> weaviate.WeaviateClient:
    """Crear cliente de Weaviate con autenticación OpenAI"""
    try:
        # Headers para OpenAI si se proporciona key
        headers = {}
        if openai_key:
            headers["X-OpenAI-Api-Key"] = openai_key
        
        # Extraer host y puerto de la URL
        # Ej: http://localhost:8082 -> host=localhost, port=8082
        url_clean = url.replace("http://", "").replace("https://", "")
        if ":" in url_clean:
            host, port_str = url_clean.split(":", 1)
            http_port = int(port_str)
            # Mapear puerto HTTP al puerto gRPC correspondiente
            if http_port == 8083:
                grpc_port = 50054  # Puerto gRPC para nuestro OXCART Weaviate
            else:
                grpc_port = 50051  # Puerto gRPC por defecto
        else:
            host = url_clean
            http_port = 8080
            grpc_port = 50051
        
        client = weaviate.connect_to_local(
            host=host,
            port=http_port,
            grpc_port=grpc_port,
            headers=headers
        )
        
        print(f"Conectado a Weaviate en {url}")
        return client
    except Exception as e:
        print(f"Error conectando a Weaviate: {e}")
        print(f"Asegúrate que Weaviate esté corriendo en {url}")
        raise

# Esquema / Colección
# --------------------------------------------
def create_oxcart_collection(client: weaviate.WeaviateClient, collection_name: str = "Oxcart") -> bool:
    """Crear la colección Oxcart con esquema optimizado para filatelia basado en philatelic_chunk_schema.py"""
    try:
        # Verificar si la colección ya existe
        if client.collections.exists(collection_name):
            print(f"ADVERTENCIA: Coleccion '{collection_name}' ya existe")
            print("INFORMACION: Usando coleccion existente")
            return True

        # Crear colección optimizada: solo 'text' se vectoriza, 'text_original' es solo filtro
        collection = client.collections.create(
            name=collection_name,
            vector_config=wvc.config.Configure.Vectors.text2vec_openai(
                name="default",
                model="text-embedding-3-large",
                # Solo vectorizar el campo 'text' (enriquecido)
                source_properties=["text"],
                # el índice HNSW va DENTRO del named vector
                vector_index_config=wvc.config.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.config.VectorDistances.COSINE
                ),
            ),
            properties=[
                # Propiedades principales
                wvc.config.Property(
                    name="chunk_id",
                    data_type=wvc.config.DataType.TEXT,
                    description="Identificador único del chunk (doc_id:page:reading_order:part)"
                ),
                wvc.config.Property(
                    name="chunk_type", 
                    data_type=wvc.config.DataType.TEXT,
                    description="Tipo de contenido (text, table, figure, caption, etc.)"
                ),
                wvc.config.Property(
                    name="text",
                    data_type=wvc.config.DataType.TEXT,
                    description="Contenido enriquecido para vectorización (embeddings)"
                ),
                wvc.config.Property(
                    name="text_original",
                    data_type=wvc.config.DataType.TEXT,
                    description="Contenido original sin enriquecimiento (para mostrar al usuario)"
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

                # Metadatos filatélicos específicos - Catálogos
                wvc.config.Property(
                    name="catalog_systems",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Sistemas de catálogo encontrados (Scott, Michel, Yvert, etc.)"
                ),
                wvc.config.Property(
                    name="catalog_numbers",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Números de catálogo específicos"
                ),
                wvc.config.Property(
                    name="scott_numbers",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Números Scott específicos para búsqueda directa"
                ),

                # Información temporal
                wvc.config.Property(name="dates", data_type=wvc.config.DataType.TEXT_ARRAY, description="Fechas normalizadas encontradas (ISO format)"),
                wvc.config.Property(name="years", data_type=wvc.config.DataType.INT_ARRAY, description="Años extraídos para filtros numéricos"),
                wvc.config.Property(name="decades", data_type=wvc.config.DataType.TEXT_ARRAY, description="Décadas (1920s, 1950s, etc.)"),

                # Apariencia y diseño
                wvc.config.Property(name="colors", data_type=wvc.config.DataType.TEXT_ARRAY, description="Colores detectados en el contenido"),
                wvc.config.Property(name="designs", data_type=wvc.config.DataType.TEXT_ARRAY, description="Elementos de diseño (coat of arms, cathedral, etc.)"),

                # Especificaciones técnicas
                wvc.config.Property(name="perforation_measurements", data_type=wvc.config.DataType.TEXT_ARRAY, description="Medidas de perforación"),
                wvc.config.Property(name="perforation_type", data_type=wvc.config.DataType.TEXT, description="Tipo de perforación (imperforate, etc.)"),
                wvc.config.Property(name="paper_type", data_type=wvc.config.DataType.TEXT, description="Tipo de papel (wove, laid, etc.)"),
                wvc.config.Property(name="printing_method", data_type=wvc.config.DataType.TEXT, description="Método de impresión (lithography, engraved, etc.)"),
                wvc.config.Property(name="watermark_type", data_type=wvc.config.DataType.TEXT, description="Tipo de marca de agua"),
                wvc.config.Property(name="gum_type", data_type=wvc.config.DataType.TEXT, description="Tipo de goma"),

                # Condición y estado
                wvc.config.Property(name="mint_status", data_type=wvc.config.DataType.TEXT, description="Estado mint (never hinged, lightly hinged, etc.)"),
                wvc.config.Property(name="used_status", data_type=wvc.config.DataType.TEXT, description="Estado usado (postally used, CTO, etc.)"),
                wvc.config.Property(name="centering", data_type=wvc.config.DataType.TEXT, description="Calidad del centrado (very fine, fine, etc.)"),
                wvc.config.Property(name="has_defects", data_type=wvc.config.DataType.BOOL, description="Indica si tiene defectos"),

                # Variedades y errores (EFO)
                wvc.config.Property(name="variety_classes", data_type=wvc.config.DataType.TEXT_ARRAY, description="Clases de variedades (overprint, color_error, etc.)"),
                wvc.config.Property(name="variety_subtypes", data_type=wvc.config.DataType.TEXT_ARRAY, description="Subtipos de variedades (inverted, double, etc.)"),

                # Costa Rica específico
                wvc.config.Property(name="is_guanacaste", data_type=wvc.config.DataType.BOOL, description="Indica si es del período Guanacaste"),
                wvc.config.Property(name="cr_personalities", data_type=wvc.config.DataType.TEXT_ARRAY, description="Personalidades costarricenses mencionadas"),
                wvc.config.Property(name="cr_geography", data_type=wvc.config.DataType.TEXT_ARRAY, description="Características geográficas de Costa Rica"),

                # Topics y clasificación
                wvc.config.Property(name="topics_primary", data_type=wvc.config.DataType.TEXT, description="Topic principal detectado"),
                wvc.config.Property(name="topics_secondary", data_type=wvc.config.DataType.TEXT_ARRAY, description="Topics secundarios"),
                wvc.config.Property(name="topics_tags", data_type=wvc.config.DataType.TEXT_ARRAY, description="Tags específicos del contenido"),
                wvc.config.Property(name="stamp_types", data_type=wvc.config.DataType.TEXT_ARRAY, description="Tipos de sellos (airmail, postage_due, etc.)"),

                # Flags booleanos
                wvc.config.Property(name="has_prices", data_type=wvc.config.DataType.BOOL, description="Indica si el chunk contiene información de precios"),
                wvc.config.Property(name="has_varieties", data_type=wvc.config.DataType.BOOL, description="Indica si contiene variedades filatélicas"),
                wvc.config.Property(name="has_catalog", data_type=wvc.config.DataType.BOOL, description="Indica si contiene referencias de catálogo"),
                wvc.config.Property(name="has_face_values", data_type=wvc.config.DataType.BOOL, description="Indica si contiene valores faciales"),
                wvc.config.Property(name="has_technical_specs", data_type=wvc.config.DataType.BOOL, description="Indica si contiene especificaciones técnicas"),

                # Calidad y confianza
                wvc.config.Property(name="quality_score", data_type=wvc.config.DataType.NUMBER, description="Puntuación de calidad del chunk (0-1)"),
                wvc.config.Property(name="confidence_score", data_type=wvc.config.DataType.NUMBER, description="Puntuación de confianza de los metadatos (0-1)"),

                # Metadatos esenciales (simplificado)
                wvc.config.Property(name="reading_order_range", data_type=wvc.config.DataType.TEXT, description="Rango de orden de lectura en la página"),
                wvc.config.Property(name="labels", data_type=wvc.config.DataType.TEXT_ARRAY, description="Labels originales del chunk (para, sec, tab, etc.)"),
            ]
        )

        print(f"EXITO: Coleccion '{collection_name}' creada exitosamente")
        print(f"VECTORIZADOR: OpenAI text-embedding-3-large")
        print(f"PROPIEDADES: {len(collection.config.get().properties)} campos definidos")
        return True

    except Exception as e:
        print(f"ERROR: Error creando coleccion: {e}")
        return False





# --------------------------------------------
# Transformación de chunks
# --------------------------------------------
def transform_chunk_to_weaviate_clean(chunk: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
    """
    Transforma un chunk LIMPIO OXCART a propiedades optimizadas para Weaviate.
    Usa solo datos esenciales, sin basura de procesamiento interno.
    
    Args:
        chunk: Chunk limpio (procesado por prepare_chunk_for_weaviate)
        doc_id: ID del documento
        
    Returns:
        Dict con propiedades listas para indexar en Weaviate
    """
    metadata = chunk.get("metadata", {})
    entities = metadata.get("entities", {})
    topics = metadata.get("topics", {})
    axes = metadata.get("axes", {})
    
    # Página desde chunk_id (más confiable que grounding)
    page_number = 1
    if ":" in chunk.get("chunk_id", ""):
        try:
            page_part = chunk["chunk_id"].split(":")[1]
            page_number = int(page_part.lstrip("0") or "1")
        except (ValueError, IndexError):
            page_number = 1
    
    # Catálogos (optimizado)
    catalogs = entities.get("catalog", [])
    catalog_systems = list({cat.get("system") for cat in catalogs if cat.get("system")})
    catalog_numbers = [cat.get("number") for cat in catalogs if cat.get("number")]
    scott_numbers = [cat.get("number") for cat in catalogs if cat.get("system") == "Scott"]
    
    # Fechas/Años (optimizado)
    dates = entities.get("dates", [])
    years, decades = [], []
    for date in dates:
        if len(date) >= 4 and date[:4].isdigit():
            y = int(date[:4])
            years.append(y)
            decades.append(f"{(y // 10) * 10}s")
    years = sorted(set(years))
    decades = sorted(set(decades))
    
    # Especificaciones técnicas (simplificado)
    perforation = entities.get("perforation", {})
    perforation_measurements = perforation.get("measurements", [])
    perforation_type = perforation.get("type", "")
    
    paper_type = entities.get("paper", {}).get("type", "")
    printing_method = entities.get("printing", {}).get("method", "")
    watermark_type = entities.get("watermark", {}).get("type", "")
    gum_type = entities.get("gum", {}).get("type", "")
    
    # Condición (simplificado)
    condition = entities.get("condition", {})
    mint_status = condition.get("mint_status", "")
    used_status = condition.get("used_status", "")
    centering = condition.get("centering", "")
    has_defects = bool(condition.get("defects", []))
    
    # Variedades
    varieties = entities.get("varieties", [])
    variety_classes = list({v.get("efo_class") for v in varieties if v.get("efo_class")})
    variety_subtypes = list({v.get("subtype") for v in varieties if v.get("subtype")})
    
    # Contexto CR
    cr_context = entities.get("costa_rica_context", {})
    is_guanacaste = cr_context.get("guanacaste_period", False)
    cr_personalities = cr_context.get("personalities", [])
    cr_geography = cr_context.get("geographic_features", [])
    
    # Topics
    topics_primary = topics.get("primary", "")
    topics_secondary = topics.get("secondary", [])
    topics_tags = topics.get("tags", [])
    stamp_types = axes.get("type", [])
    
    # Flags booleanos
    has_catalog = bool(catalogs)
    has_prices = bool(entities.get("prices", []))
    has_varieties = bool(varieties)
    has_face_values = bool(entities.get("values", []))
    has_technical_specs = any([perforation_measurements, paper_type, printing_method, watermark_type, gum_type])
    
    # Scores
    quality_score = metadata.get("quality_score", 0.5)
    confidence_score = topics.get("confidence", 0.5)
    
    return {
        # Campos principales
        "chunk_id": chunk.get("chunk_id", ""),
        "chunk_type": chunk.get("chunk_type", "text"),
        "text": chunk.get("text", ""),  # ENRIQUECIDO - se vectoriza
        "text_original": chunk.get("text_original", ""),  # ORIGINAL - para mostrar usuario
        "doc_id": doc_id,
        "page_number": page_number,
        
        # Metadatos básicos
        "labels": metadata.get("labels", []),
        "reading_order_range": str(metadata.get("reading_order_range", [])),
        
        # Catálogos
        "catalog_systems": catalog_systems,
        "catalog_numbers": catalog_numbers,
        "scott_numbers": scott_numbers,
        
        # Temporal
        "dates": dates,
        "years": years,
        "decades": decades,
        
        # Apariencia
        "colors": entities.get("colors", []),
        "designs": entities.get("designs", []),
        
        # Técnico
        "perforation_measurements": perforation_measurements,
        "perforation_type": perforation_type,
        "paper_type": paper_type,
        "printing_method": printing_method,
        "watermark_type": watermark_type,
        "gum_type": gum_type,
        
        # Condición
        "mint_status": mint_status,
        "used_status": used_status,
        "centering": centering,
        "has_defects": has_defects,
        
        # Variedades
        "variety_classes": variety_classes,
        "variety_subtypes": variety_subtypes,
        
        # Costa Rica
        "is_guanacaste": is_guanacaste,
        "cr_personalities": cr_personalities,
        "cr_geography": cr_geography,
        
        # Topics
        "topics_primary": topics_primary,
        "topics_secondary": topics_secondary,
        "topics_tags": topics_tags,
        "stamp_types": stamp_types,
        
        # Flags
        "has_catalog": has_catalog,
        "has_prices": has_prices,
        "has_varieties": has_varieties,
        "has_face_values": has_face_values,
        "has_technical_specs": has_technical_specs,
        
        # Calidad
        "quality_score": quality_score,
        "confidence_score": confidence_score,
    }


# --------------------------------------------
# Transformación de chunks (LEGACY)
# --------------------------------------------
def transform_chunk_to_weaviate(chunk: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
    """Transforma un chunk OXCART a propiedades para Weaviate."""
    metadata = chunk.get("metadata", {})
    entities = metadata.get("entities", {})
    topics = metadata.get("topics", {})
    axes = metadata.get("axes", {})
    grounding = chunk.get("grounding", [])

    # Página
    page_number = 1
    if grounding:
        page_number = grounding[0].get("page", 1)
    elif ":" in chunk.get("chunk_id", ""):
        try:
            page_part = chunk["chunk_id"].split(":")[1]
            page_number = int(page_part.lstrip("0") or "1")
        except (ValueError, IndexError):
            page_number = 1

    # Catálogos
    catalogs = entities.get("catalog", [])
    catalog_systems = list({cat.get("system") for cat in catalogs if cat.get("system")})
    catalog_numbers = [cat.get("number") for cat in catalogs if cat.get("number")]
    scott_numbers = [cat.get("number") for cat in catalogs if cat.get("system") == "Scott"]

    # Fechas/Años/Décadas
    dates = entities.get("dates", [])
    years, decades = [], []
    for date in dates:
        if len(date) >= 4 and date[:4].isdigit():
            y = int(date[:4])
            years.append(y)
            decades.append(f"{(y // 10) * 10}s")
    years = sorted(set(years))
    decades = sorted(set(decades))

    # Apariencia
    colors = entities.get("colors", [])
    designs = entities.get("designs", [])

    # Especificaciones
    perforation = entities.get("perforation", {})
    perforation_measurements = perforation.get("measurements", [])
    perforation_type = perforation.get("type", "")

    paper_type = entities.get("paper", {}).get("type", "")
    printing_method = entities.get("printing", {}).get("method", "")
    watermark_type = entities.get("watermark", {}).get("type", "")
    gum_type = entities.get("gum", {}).get("type", "")

    # Condición
    condition = entities.get("condition", {})
    mint_status = condition.get("mint_status", "")
    used_status = condition.get("used_status", "")
    centering = condition.get("centering", "")
    defects = condition.get("defects", [])
    has_defects = bool(defects)

    # Variedades
    varieties = entities.get("varieties", [])
    variety_classes = list({v.get("class") for v in varieties if v.get("class")})
    variety_subtypes = list({v.get("subtype") for v in varieties if v.get("subtype")})

    # Contexto CR
    cr_context = entities.get("costa_rica_context", {})
    is_guanacaste = cr_context.get("guanacaste_period", False)
    cr_personalities = cr_context.get("personalities", [])
    cr_geography = cr_context.get("geographic_features", [])

    # Topics/clasificación
    topics_primary = topics.get("primary", "")
    topics_secondary = topics.get("secondary", [])
    topics_tags = topics.get("tags", [])
    stamp_types = axes.get("type", [])

    # Flags
    has_catalog = bool(catalogs)
    has_prices = bool(entities.get("prices", []))
    has_varieties = bool(varieties)
    has_face_values = bool(entities.get("values", []))
    has_technical_specs = any([perforation_measurements, paper_type, printing_method, watermark_type, gum_type])

    # Scores
    quality_score = metadata.get("quality_score", 0.5)
    confidence_score = topics.get("confidence", 0.5)

    reading_order_range = str(metadata.get("reading_order_range", []))

    return {
        "chunk_id": chunk.get("chunk_id", ""),
        "chunk_type": chunk.get("chunk_type", "text"),
        "text": chunk.get("text", ""),
        "doc_id": doc_id,
        "page_number": page_number,

        "catalog_systems": catalog_systems,
        "catalog_numbers": catalog_numbers,
        "scott_numbers": scott_numbers,

        "dates": dates,
        "years": years,
        "decades": decades,

        "colors": colors,
        "designs": designs,

        "perforation_measurements": perforation_measurements,
        "perforation_type": perforation_type,
        "paper_type": paper_type,
        "printing_method": printing_method,
        "watermark_type": watermark_type,
        "gum_type": gum_type,

        "mint_status": mint_status,
        "used_status": used_status,
        "centering": centering,
        "has_defects": has_defects,

        "variety_classes": variety_classes,
        "variety_subtypes": variety_subtypes,

        "is_guanacaste": is_guanacaste,
        "cr_personalities": cr_personalities,
        "cr_geography": cr_geography,

        "topics_primary": topics_primary,
        "topics_secondary": topics_secondary,
        "topics_tags": topics_tags,
        "stamp_types": stamp_types,

        "has_catalog": has_catalog,
        "has_prices": has_prices,
        "has_varieties": has_varieties,
        "has_face_values": has_face_values,
        "has_technical_specs": has_technical_specs,

        "quality_score": quality_score,
        "confidence_score": confidence_score,

        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "reading_order_range": reading_order_range,
    }

# --------------------------------------------
# Validación y preparación de chunks
# --------------------------------------------
def validate_and_prepare_chunks(chunks: List[Dict[str, Any]], doc_id: str) -> Dict[str, Any]:
    """
    Valida y prepara chunks para indexación, manejando chunks demasiado largos.
    
    Args:
        chunks: Lista de chunks a validar
        doc_id: ID del documento
        
    Returns:
        Dict con chunks válidos, estadísticas y logs de problemas
    """
    # Configuración de límites para OpenAI text-embedding-3-large
    MAX_TOKENS = 3000  # Límite EXTREMADAMENTE seguro (OpenAI permite 8192, dejamos margen muy amplio)
    CHARS_PER_TOKEN = 4  # Aproximación para español  
    MAX_CHARS = MAX_TOKENS * CHARS_PER_TOKEN  # ~12,000 caracteres
    
    valid_chunks = []
    truncated_chunks = []
    skipped_chunks = []
    statistics = {
        "total_chunks": len(chunks),
        "valid_chunks": 0,
        "truncated_chunks": 0,
        "skipped_chunks": 0,
        "total_chars_saved": 0
    }
    
    print(f"🔍 Validando {len(chunks)} chunks para documento {doc_id}")
    print(f"   📏 Límite: {MAX_CHARS:,} caracteres ({MAX_TOKENS} tokens)")
    
    for i, chunk in enumerate(chunks):
        chunk_text = chunk.get("text", "")
        chunk_length = len(chunk_text)
        
        if chunk_length <= MAX_CHARS:
            # Chunk válido, no requiere modificación pero marcar como no truncado
            chunk_copy = chunk.copy()
            chunk_copy["truncated"] = False  # Marcar explícitamente como no truncado
            
            valid_chunks.append(chunk_copy)
            statistics["valid_chunks"] += 1
            
        elif chunk_length > MAX_CHARS:
            # Chunk demasiado largo, truncar
            truncated_text = chunk_text[:MAX_CHARS]
            
            # Crear copia del chunk con texto truncado
            truncated_chunk = chunk.copy()
            truncated_chunk["text"] = truncated_text
            
            # Marcar chunk como truncado (flag principal)
            truncated_chunk["truncated"] = True
            
            # Agregar metadatos de truncado
            if "metadata" not in truncated_chunk:
                truncated_chunk["metadata"] = {}
            truncated_chunk["metadata"]["truncated"] = True
            truncated_chunk["metadata"]["original_length"] = chunk_length
            truncated_chunk["metadata"]["truncated_length"] = len(truncated_text)
            truncated_chunk["metadata"]["chars_removed"] = chunk_length - len(truncated_text)
            
            # Preservar texto original para UI
            if "text_original" not in truncated_chunk:
                truncated_chunk["text_original"] = chunk_text
            
            valid_chunks.append(truncated_chunk)
            truncated_chunks.append({
                "index": i,
                "chunk_id": chunk.get("chunk_id", f"chunk_{i}"),
                "original_length": chunk_length,
                "truncated_length": len(truncated_text),
                "chars_removed": chunk_length - len(truncated_text)
            })
            
            statistics["truncated_chunks"] += 1
            statistics["total_chars_saved"] += chunk_length - len(truncated_text)
    
    # Mostrar estadísticas
    if statistics["truncated_chunks"] > 0:
        print(f"   ✂️ Chunks truncados: {statistics['truncated_chunks']}")
        print(f"   💾 Caracteres removidos: {statistics['total_chars_saved']:,}")
        
        # Mostrar algunos ejemplos de chunks truncados
        for i, trunc_info in enumerate(truncated_chunks[:3]):
            print(f"      • {trunc_info['chunk_id']}: {trunc_info['original_length']:,} → {trunc_info['truncated_length']:,} chars")
        if len(truncated_chunks) > 3:
            print(f"      • ... y {len(truncated_chunks) - 3} más")
    
    print(f"   ✅ Chunks válidos: {statistics['valid_chunks']}")
    print(f"   📊 Tasa de éxito: {(statistics['valid_chunks']/statistics['total_chunks'])*100:.1f}%")
    
    return {
        "valid_chunks": valid_chunks,
        "truncated_info": truncated_chunks,
        "skipped_info": skipped_chunks,
        "statistics": statistics
    }

# --------------------------------------------
# Batch index
# --------------------------------------------
def batch_index_chunks(
    client: weaviate.WeaviateClient,
    chunks: List[Dict[str, Any]],
    doc_id: str,
    collection_name: str = "Oxcart",
    batch_size: int = 50,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Indexa chunks en lotes usando insert_many con reintentos, rate limiting y manejo de chunks largos.
    
    Args:
        client: Cliente Weaviate
        chunks: Lista de chunks filtrados (sin chunks ya indexados)
        doc_id: ID del documento
        collection_name: Nombre de la colección
        batch_size: Tamaño del lote
        progress_callback: Función callback para actualizar progress bar
    """
    import time
    import random
    from typing import Optional
    
    if not chunks:
        return {
            "total_chunks": 0,
            "successful": 0,
            "errors": [],
            "success_rate": 100.0,
            "successful_chunk_indices": [],
            "validation_stats": {}
        }
    
    # PASO 1: Validar y preparar chunks para evitar errores de OpenAI
    print(f"🔍 VALIDACIÓN PREVIA DE CHUNKS")
    validation_result = validate_and_prepare_chunks(chunks, doc_id)
    
    # Usar chunks validados (truncados si es necesario)
    validated_chunks = validation_result["valid_chunks"]
    validation_stats = validation_result["statistics"]
    
    if not validated_chunks:
        print("❌ No hay chunks válidos para indexar después de validación")
        return {
            "total_chunks": len(chunks),
            "successful": 0,
            "errors": ["No chunks válidos después de validación"],
            "success_rate": 0.0,
            "successful_chunk_indices": [],
            "validation_stats": validation_stats
        }
    
    # PASO 2: Indexación con chunks validados
    collection = client.collections.get(collection_name)
    total_original_chunks = len(chunks)
    total_valid_chunks = len(validated_chunks)
    successful = 0
    errors = []
    successful_chunk_indices = []  # Para marcar chunks como indexados

    print(f"\n🚀 INICIANDO INDEXACIÓN ROBUSTA")
    print(f"   📄 Documento: {doc_id}")
    print(f"   📦 Chunks originales: {total_original_chunks}")
    print(f"   ✅ Chunks válidos: {total_valid_chunks}")
    if validation_stats["truncated_chunks"] > 0:
        print(f"   ✂️ Chunks truncados: {validation_stats['truncated_chunks']}")
    print(f"   📦 Lotes de {batch_size} chunks con máximo 3 reintentos")

    for i in range(0, total_valid_chunks, batch_size):
        batch = validated_chunks[i:i + batch_size]
        batch_indices = list(range(i, min(i + batch_size, total_valid_chunks)))
        batch_num = (i // batch_size) + 1
        total_batches = (total_valid_chunks + batch_size - 1) // batch_size
        
        # Reintentos para este lote
        max_retries = 3
        retry_count = 0
        batch_success = False
        
        while retry_count <= max_retries and not batch_success:
            try:
                if retry_count > 0:
                    print(f"   🔄 Reintento {retry_count}/{max_retries} para lote {batch_num}")
                
                # Usar función de transformación limpia optimizada
                objs = [transform_chunk_to_weaviate_clean(c, doc_id) for c in batch]
                result = collection.data.insert_many(objs)

                # 📌 v4: BatchObjectReturn con dicts indexados por índice original
                batch_successful = len(result.uuids)
                successful += batch_successful
                
                # Marcar chunks exitosos para el guardado final
                if batch_successful > 0:
                    # Todos los chunks que no tienen error se consideran exitosos
                    failed_indices = set()
                    if result.has_errors and result.errors:
                        failed_indices = {int(idx) for idx in result.errors.keys()}
                    
                    for local_idx in range(len(batch)):
                        if local_idx not in failed_indices:
                            global_idx = batch_indices[local_idx]
                            successful_chunk_indices.append(global_idx)

                if result.has_errors and result.errors:
                    # Guardar errores para logging
                    for idx, err in list(result.errors.items()):
                        errors.append({
                            "batch": batch_num, 
                            "index": int(idx), 
                            "error": err.message,
                            "retry_count": retry_count
                        })

                print(f"   📦 Lote {batch_num}/{total_batches}: {batch_successful}/{len(batch)} exitosos")
                if result.has_errors:
                    print(f"      ⚠️ Errores: {len(result.errors)} en este lote")
                
                # Actualizar progress bar si se proporcionó callback
                if progress_callback:
                    progress_callback(batch_successful)
                
                batch_success = True  # Salir del bucle de reintentos
                
            except Exception as e:
                error_msg = str(e)
                print(f"      ❌ Error en lote {batch_num} (intento {retry_count + 1}): {error_msg}")
                
                # Detectar rate limit (HTTP 429)
                is_rate_limit = "429" in error_msg or "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower()
                
                if is_rate_limit:
                    # Backoff exponencial para rate limits
                    wait_time = min(60, (2 ** retry_count) * 5 + random.uniform(1, 3))
                    print(f"      ⏳ Rate limit detectado, esperando {wait_time:.1f} segundos...")
                    time.sleep(wait_time)
                elif retry_count < max_retries:
                    # Backoff más corto para otros errores
                    wait_time = (retry_count + 1) * 2
                    print(f"      ⏳ Esperando {wait_time}s antes del siguiente intento...")
                    time.sleep(wait_time)
                
                retry_count += 1
                
                if retry_count > max_retries:
                    # Error final después de todos los reintentos
                    errors.append({
                        "batch": batch_num, 
                        "error": f"Falló después de {max_retries} reintentos: {error_msg}",
                        "final_failure": True
                    })

    success_rate = (successful / total_valid_chunks) * 100 if total_valid_chunks else 0
    print(f"   📊 Resumen final: {successful}/{total_valid_chunks} chunks válidos indexados ({success_rate:.1f}%)")
    
    if validation_stats["truncated_chunks"] > 0:
        print(f"   ✂️ Total chunks truncados exitosamente: {validation_stats['truncated_chunks']}")
        print(f"   💾 Total caracteres removidos: {validation_stats['total_chars_saved']:,}")

    return {
        "total_chunks": total_original_chunks,  # Total original
        "total_valid_chunks": total_valid_chunks,  # Chunks procesables
        "successful": successful,
        "errors": errors,
        "success_rate": success_rate,
        "successful_chunk_indices": successful_chunk_indices,
        "validation_stats": validation_stats,  # Estadísticas de truncado
        "truncated_info": validation_result.get("truncated_info", [])  # Detalles de chunks truncados
    }

# --------------------------------------------
# Indexar documento completo
# --------------------------------------------
def index_philatelic_document_clean(
    client: weaviate.WeaviateClient,
    document: Dict[str, Any],
    collection_name: str = "Oxcart",
    prepare_chunks: bool = True
) -> Dict[str, Any]:
    """
    Indexa documento filatélico usando chunks limpios optimizados para Weaviate.
    
    Args:
        client: Cliente Weaviate
        document: Documento OXCART procesado
        collection_name: Nombre de la colección
        prepare_chunks: Si True, limpia chunks antes de indexar
        
    Returns:
        Diccionario con resultados de indexación
    """
    doc_id = document.get("doc_id", "unknown")
    chunks = document.get("chunks", [])

    if not chunks:
        print(f"ERROR: Documento {doc_id} no tiene chunks para indexar")
        return {"success": False, "error": "No chunks found"}

    print(f"📄 Indexando documento LIMPIO: {doc_id}")
    print(f"   📊 Chunks originales: {len(chunks)}")
    print(f"   📄 Páginas: {document.get('page_count', 'unknown')}")
    
    # Preparar chunks limpios si es necesario
    if prepare_chunks:
        # Importar función desde philatelic_chunk_logic
        try:
            from philatelic_chunk_logic import prepare_chunks_batch_for_weaviate
            clean_chunks = prepare_chunks_batch_for_weaviate(chunks)
            print(f"   🧹 Chunks limpios: {len(clean_chunks)} (eliminados {len(chunks) - len(clean_chunks)})")
        except ImportError:
            print("   ⚠️ No se pudo importar prepare_chunks_batch_for_weaviate, usando chunks originales")
            clean_chunks = chunks
    else:
        clean_chunks = chunks

    # Indexar chunks limpios
    results = batch_index_chunks(client, clean_chunks, doc_id, collection_name)

    if results["successful"] > 0:
        print(f"✅ Documento {doc_id} indexado exitosamente (modo limpio)")
        print(f"   📊 {results['successful']}/{len(clean_chunks)} chunks indexados")
        if prepare_chunks:
            print(f"   🎯 Solo 'text' enriquecido vectorizado, 'text_original' disponible para UI")
    else:
        print(f"❌ Error indexando documento {doc_id}")

    return results


# --------------------------------------------
# Indexar documento completo (LEGACY)
# --------------------------------------------
def index_philatelic_document(
    client: weaviate.WeaviateClient,
    document: Dict[str, Any],
    collection_name: str = "Oxcart",
    progress_callback=None
) -> Dict[str, Any]:
    """
    Indexa documento filatélico con filtrado de chunks ya indexados y persistencia de estado.
    
    Args:
        client: Cliente Weaviate
        document: Documento OXCART con chunks
        collection_name: Nombre de la colección
        progress_callback: Callback para progress bar
    
    Returns:
        Diccionario con resultados de indexación y chunks marcados como indexados
    """
    doc_id = document.get("doc_id", "unknown")
    chunks = document.get("chunks", [])

    if not chunks:
        print(f"ERROR: Documento {doc_id} no tiene chunks para indexar")
        return {"success": False, "error": "No chunks found"}

    # Filtrar chunks ya indexados
    chunks_to_index = []
    chunks_already_indexed = 0
    
    for i, chunk in enumerate(chunks):
        if chunk.get("indexed", False):
            chunks_already_indexed += 1
        else:
            chunks_to_index.append((i, chunk))  # Guardamos índice original

    print(f"📄 Indexando documento: {doc_id}")
    print(f"   📊 Total chunks: {len(chunks)}")
    print(f"   ✅ Ya indexados: {chunks_already_indexed}")
    print(f"   ⏳ Pendientes: {len(chunks_to_index)}")
    print(f"   📄 Páginas: {document.get('page_count', 'unknown')}")

    if not chunks_to_index:
        print(f"🎉 Documento {doc_id} ya está completamente indexado")
        return {
            "total_chunks": len(chunks),
            "successful": chunks_already_indexed,
            "errors": [],
            "success_rate": 100.0,
            "already_indexed": True
        }

    # Validar y preparar chunks (truncar si es necesario)
    chunks_only = [chunk for _, chunk in chunks_to_index]
    
    print(f"🔍 VALIDACIÓN PREVIA DE CHUNKS")
    validation_result = validate_and_prepare_chunks(chunks_only, doc_id)
    
    # Usar chunks validados (puede incluir chunks truncados)
    validated_chunks = validation_result["valid_chunks"]
    validation_stats = validation_result["statistics"]
    truncated_info = validation_result["truncated_info"]
    
    # Marcar chunks truncados Y no truncados en el documento original ANTES de indexar
    chunks_truncated_marked = 0
    chunks_not_truncated_marked = 0
    
    # Marcar todos los chunks con su estado de truncado
    for local_idx, validated_chunk in enumerate(validated_chunks):
        if local_idx < len(chunks_to_index):
            original_idx, _ = chunks_to_index[local_idx]
            
            if validated_chunk.get("truncated", False):
                # Chunk fue truncado
                document["chunks"][original_idx]["truncated"] = True
                document["chunks"][original_idx]["text_original"] = document["chunks"][original_idx]["text"]
                document["chunks"][original_idx]["text"] = validated_chunk["text"]
                chunks_truncated_marked += 1
            else:
                # Chunk NO fue truncado (marcar explícitamente para trazabilidad)
                document["chunks"][original_idx]["truncated"] = False
                chunks_not_truncated_marked += 1
    
    # Indexar chunks validados
    results = batch_index_chunks(
        client, 
        validated_chunks,  # Usar chunks validados/truncados
        doc_id, 
        collection_name, 
        progress_callback=progress_callback
    )
    
    # Añadir información de validación a los resultados
    results["validation_stats"] = validation_stats
    results["chunks_truncated_marked"] = chunks_truncated_marked
    results["chunks_not_truncated_marked"] = chunks_not_truncated_marked

    # Marcar chunks exitosos como indexados en el documento original
    successful_indices = results.get("successful_chunk_indices", [])
    chunks_marked = 0
    
    if successful_indices:
        for local_idx in successful_indices:
            if local_idx < len(chunks_to_index):
                original_idx, _ = chunks_to_index[local_idx]
                document["chunks"][original_idx]["indexed"] = True
                chunks_marked += 1

    # Actualizar estadísticas
    results["chunks_marked_as_indexed"] = chunks_marked
    results["total_chunks"] = len(chunks)
    results["chunks_already_indexed"] = chunks_already_indexed

    if results["successful"] > 0:
        print(f"✅ Documento {doc_id} indexado exitosamente")
        print(f"   📝 Chunks marcados como indexados: {chunks_marked}")
    else:
        print(f"❌ Error indexando documento {doc_id}")

    return results

# --------------------------------------------
# Búsqueda semántica
# --------------------------------------------
def _year_list_from_range(r: List[int]) -> List[int]:
    """Convierte [min, max] en lista inclusiva de años para usar contains_any sobre INT_ARRAY."""
    if not r or len(r) != 2:
        return []
    a, b = int(r[0]), int(r[1])
    if a > b:
        a, b = b, a
    return list(range(a, b + 1))

def _build_filters(filters: Optional[Dict[str, Any]]):
    if not filters:
        return None
    conditions = []

    if filters.get("chunk_type"):
        conditions.append(wvc.query.Filter.by_property("chunk_type").equal(filters["chunk_type"]))
    if filters.get("catalog_system"):
        conditions.append(wvc.query.Filter.by_property("catalog_systems").contains_any([filters["catalog_system"]]))
    if filters.get("scott_numbers"):
        scott_value = filters["scott_numbers"]
        if isinstance(scott_value, list):
            # Multiple Scott numbers - use list directly
            conditions.append(wvc.query.Filter.by_property("scott_numbers").contains_any(scott_value))
        else:
            # Single Scott number - wrap in list
            conditions.append(wvc.query.Filter.by_property("scott_numbers").contains_any([scott_value]))
    if filters.get("year_range"):
        y0, y1 = filters["year_range"]
        y0, y1 = int(min(y0, y1)), int(max(y0, y1))
        conditions.append(wvc.query.Filter.by_property("years").contains_any(list(range(y0, y1 + 1))))
    if filters.get("color"):
        conditions.append(wvc.query.Filter.by_property("colors").contains_any([filters["color"]]))
    if filters.get("topic"):
        conditions.append(
            wvc.query.Filter.by_property("topics_primary").equal(filters["topic"]) |
            wvc.query.Filter.by_property("topics_secondary").contains_any([filters["topic"]])
        )
    if filters.get("has_varieties"):
        conditions.append(wvc.query.Filter.by_property("has_varieties").equal(True))
    if filters.get("is_guanacaste"):
        conditions.append(wvc.query.Filter.by_property("is_guanacaste").equal(True))
    if filters.get("has_technical_specs"):
        conditions.append(wvc.query.Filter.by_property("has_technical_specs").equal(True))

    if not conditions:
        return None
    f = conditions[0]
    for c in conditions[1:]:
        f = f & c
    return f

def _distance_to_similarity(distance: Optional[float], metric: str = "cosine") -> Optional[float]:
    if distance is None:
        return None
    if metric == "cosine":
        # en Weaviate: menor distance = mayor similitud
        return max(0.0, min(1.0, 1.0 - float(distance)))
    elif metric in ("l2", "euclidean"):
        return 1.0 / (1.0 + float(distance))
    elif metric == "dot":  # heurístico
        return 1.0 - (float(distance) / 2.0)
    return None

def search_chunks_semantic(
    client,
    query: str,
    collection_name: str = "Oxcart",
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    mode: str = "vector",        # "vector" (near_text) | "hybrid" | "bm25"
    alpha: float = 0.35,          # solo para hybrid
    distance_metric: str = "cosine"  # para convertir distance->similarity
) -> List[Dict[str, Any]]:
    """
    Búsqueda avanzada.
    - vector: near_text (devuelve distance; calculamos similarity y la exponemos también como 'score').
    - hybrid: hybrid(query, alpha) (devuelve metadata.score).
    - bm25: bm25(query) (devuelve metadata.score).
    """
    coll = client.collections.get(collection_name)
    f = _build_filters(filters)

    # Ejecutar consulta según modo
    if mode == "hybrid":
        resp = coll.query.hybrid(
            query=query,
            alpha=alpha,
            limit=limit,
            filters=f,
            return_properties=[
                "chunk_id","chunk_type","text","text_original","doc_id","page_number",
                "catalog_systems","catalog_numbers","scott_numbers","years","colors",
                "topics_primary","variety_classes","has_catalog","has_prices","has_varieties",
                "is_guanacaste","quality_score"
            ],
            return_metadata=wvc.query.MetadataQuery(score=True, distance=True),
        )
    elif mode == "bm25":
        resp = coll.query.bm25(
            query=query,
            limit=limit,
            filters=f,
            return_properties=[
                "chunk_id","chunk_type","text","doc_id","page_number",
                "catalog_systems","catalog_numbers","scott_numbers","years","colors",
                "topics_primary","variety_classes","has_catalog","has_prices","has_varieties",
                "is_guanacaste","quality_score"
            ],
            return_metadata=wvc.query.MetadataQuery(score=True),
        )
    else:  # "vector" por defecto
        resp = coll.query.near_text(
            query=query,
            limit=limit,
            filters=f,
            return_properties=[
                "chunk_id","chunk_type","text","doc_id","page_number",
                "catalog_systems","catalog_numbers","scott_numbers","years","colors",
                "topics_primary","variety_classes","has_catalog","has_prices","has_varieties",
                "is_guanacaste","quality_score"
            ],
            return_metadata=wvc.query.MetadataQuery(distance=True),  # score no aplica en near_text
        )

    results = []
    for obj in (resp.objects or []):
        props = obj.properties or {}
        meta = getattr(obj, "metadata", None)
        distance = getattr(meta, "distance", None) if meta else None
        hybrid_score = getattr(meta, "score", None) if meta else None

        # Si es vector: calculamos similarity y la damos también como 'score' (compat)
        similarity = _distance_to_similarity(distance, metric=distance_metric)
        score_out = hybrid_score if hybrid_score is not None else (similarity if similarity is not None else 0.0)
        
        ############# Delete duplicates pics in text_original ##################
        figure_pattern = r'(!\[([^\]]*)\]\([^)]+\))'
        # Buscar figuras en el contenido original si está disponible
        original_content = props.get("text_original", "")
        
        # Extraer todas las figuras del contenido original
        figures = re.findall(figure_pattern, original_content)
        
        # Eliminar duplicados manteniendo el orden
        seen_figures = set()
        unique_figures = []
        for fig in figures:
            # Usar el path de la imagen como identificador único (ignorando el alt text)
            img_path = re.search(r'\]\(([^)]+)\)', fig[0])
            if img_path:
                img_identifier = img_path.group(1)
                if img_identifier not in seen_figures:
                    seen_figures.add(img_identifier)
                    unique_figures.append(fig)
        
        # Verificar qué figuras ya están en el contenido comprimido
        existing_figures = set()
        for fig in unique_figures:
            if fig[0] in original_content:
                img_path = re.search(r'\]\(([^)]+)\)', fig[0])
                if img_path:
                    existing_figures.add(img_path.group(1))
        
        # Agregar solo las figuras que faltan
        missing_figures = []
        for fig in unique_figures:
            img_path = re.search(r'\]\(([^)]+)\)', fig[0])
            if img_path and img_path.group(1) not in existing_figures:
                missing_figures.append(fig[0])
        
        # Si hay figuras faltantes, agregarlas al final
        if missing_figures:
            figures_text = "\n\n" + "\n".join(missing_figures)
            original_content = original_content + figures_text
        ############# Delete duplicates pics in text_original ##################

        results.append({
            "uuid": str(obj.uuid),
            "score": score_out,                  # ↑ alto = mejor (hybrid o similarity)
            "similarity": similarity,            # útil si quieres distinguir
            "distance": distance,                # en vector search, bajo = mejor
            "chunk_id": props.get("chunk_id", ""),
            "chunk_type": props.get("chunk_type", ""),
            "text": original_content,
            "doc_id": props.get("doc_id", ""),
            "page_number": props.get("page_number", 0),
            "catalog_systems": props.get("catalog_systems", []),
            "catalog_numbers": props.get("catalog_numbers", []),
            "scott_numbers": props.get("scott_numbers", []),
            "years": props.get("years", []),
            "colors": props.get("colors", []),
            "topics_primary": props.get("topics_primary", ""),
            "variety_classes": props.get("variety_classes", []),
            "has_catalog": props.get("has_catalog", False),
            "has_prices": props.get("has_prices", False),
            "has_varieties": props.get("has_varieties", False),
            "is_guanacaste": props.get("is_guanacaste", False),
            "quality_score": props.get("quality_score", 0.0),
            "mode": mode,
        })
    return results

# --------------------------------------------
# Estadísticas
# --------------------------------------------
def get_collection_stats(client: weaviate.WeaviateClient, collection_name: str = "Oxcart", limit: int = 1000) -> Dict[str, Any]:
    """
    Estadísticas de la colección usando aggregate.over_all y GroupByAggregate.
    
    Args:
        client: Cliente de Weaviate
        collection_name: Nombre de la colección
        limit: Límite máximo de grupos para documentos y tipos de chunks (default: 1000)
    
    Returns:
        Diccionario con estadísticas incluyendo información de límites alcanzados
    """
    try:
        collection = client.collections.get(collection_name)

        # Total
        total_count = collection.aggregate.over_all(total_count=True).total_count

        # Por documento (con límite)
        docs_response = collection.aggregate.over_all(
            group_by=wvc.aggregate.GroupByAggregate(prop="doc_id", limit=limit)
        )
        doc_stats = {}
        for g in docs_response.groups:
            doc_stats[g.grouped_by.value] = g.total_count

        # Por tipo de chunk (con límite)
        types_response = collection.aggregate.over_all(
            group_by=wvc.aggregate.GroupByAggregate(prop="chunk_type", limit=limit)
        )
        type_stats = {}
        for g in types_response.groups:
            type_stats[g.grouped_by.value] = g.total_count

        # Detectar si se alcanzó el límite
        docs_limited = len(doc_stats) >= limit
        types_limited = len(type_stats) >= limit

        result = {
            "total_chunks": total_count,
            "documents": doc_stats,
            "chunk_types": type_stats,
            "total_documents": len(doc_stats),
            "limit_used": limit,
            "docs_limited": docs_limited,
            "types_limited": types_limited,
        }

        # Agregar advertencias si se alcanzó el límite
        if docs_limited:
            result["warning_docs"] = f"⚠️ Se alcanzó el límite de {limit} documentos. Puede haber más documentos únicos."
        
        if types_limited:
            result["warning_types"] = f"⚠️ Se alcanzó el límite de {limit} tipos de chunks. Puede haber más tipos."

        return result

    except Exception as e:
        print(f"❌ Error obteniendo estadísticas: {e}")
        return {}

print("Philatelic Weaviate Integration v2.1 cargado exitosamente")
print("Funciones disponibles:")
print("   - create_weaviate_client()")
print("   - create_oxcart_collection()")
print("   - index_philatelic_document()")
print("   - search_chunks_semantic()")
print("   - get_collection_stats()")