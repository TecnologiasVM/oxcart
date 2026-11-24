# OXCART RAG - Advanced Philatelic Pattern System v3.0

> Historical notes of the 2025 pipeline, not a description of what is served. Their figures were not measured
> in this repository's evaluation; what is served, and what was measured, is in the [README](../README.md) and
> [EVALUATION.md](../EVALUATION.md).

## 📖 Overview

El sistema avanzado de patrones filatélicos v3.0 es un motor de enriquecimiento de metadatos especializado para investigación filatélica profesional. Diseñado específicamente para integrarse con Weaviate vector database, proporciona extracción automática y clasificación de metadatos filatélicos con precisión y exhaustividad sin precedentes.

## 🎯 Características Principales

### 1. **Sistemas de Catálogos Internacionales**
- **Scott**: Patrón robusto para todas las variaciones (Scott 20, scott #a43, SCOTT No. 147, etc.)
- **Michel**: Catálogo alemán (Michel 247, Michel-Nr. 15a, Mi. 345)
- **Yvert & Tellier**: Catálogo francés (Yvert 123, Y&T 45a)
- **Zumstein**: Catálogo suizo (Zumstein 67, Zum. 15b)
- **Stanley Gibbons**: Catálogo británico (SG 78, Gibbons No. 234)

### 2. **Especificaciones Técnicas Avanzadas**
- **Perforación**: Medidas exactas (12x11½), tipos (comb perf, line perf), imperforados
- **Papel**: Tipos (wove, laid, granite), grosor, características especiales
- **Marca de Agua**: Tipos, posición (inverted, sideways), patrones específicos
- **Impresión**: Métodos (lithography, photogravure, engraving)
- **Goma**: Condición (original, regummed, no gum)

### 3. **Clasificación EFO (Errores, Rarezas y Curiosidades)**
- **Errores de Sobrecarga**: Invertida, doble, desplazada
- **Errores de Color**: Desplazamiento, color faltante, color incorrecto
- **Impresiones Especiales**: Espejo, invertida, doble impresión
- **Confianza y Clasificación**: Sistema de scoring automático

### 4. **Evaluación de Condición**
- **Estado Nuevo**: MNH, MLH, MH, MNG con clasificación precisa
- **Estado Usado**: CTO, postally used, first day cancel
- **Centrado**: Perfect, VF, F, VG con detección automática
- **Defectos**: Creases, thins, stains, tears

### 5. **Contexto Específico de Costa Rica**
- **Período Guanacaste**: Detección automática 1885-1891
- **Personalidades**: Jesús Jiménez, José Figueres, etc.
- **Geografía**: Volcanes, cordilleras, puertos
- **Historia Postal**: Períodos coloniales, republicanos, modernos

### 6. **Optimización para Weaviate**
- **Propiedades Indexables**: Filtrado rápido por catálogo, fecha, tipo
- **Jerarquías Taxonómicas**: Country > Period > Series > Stamp
- **Scoring de Calidad**: Métricas automáticas de completitud y precisión

## 🔧 Implementación Técnica

### Funciones Principales

```python
# Enriquecimiento completo de chunk
enrich_chunk_advanced_philatelic(chunk)

# Extracción específica de catálogos
extract_all_catalog_numbers(text)

# Clasificación de variedades EFO
classify_efo_varieties(text)

# Especificaciones técnicas
extract_technical_specs(text)

# Evaluación de condición
extract_condition_assessment(text)

# Contexto de Costa Rica
classify_costa_rica_context(text)

# Propiedades para Weaviate
generate_weaviate_properties(metadata)
```

### Estructura de Metadatos

```python
metadata = {
    "entities": {
        "catalog": [
            {"system": "Scott", "number": "C1"},
            {"system": "Michel", "number": "247"}
        ],
        "dates": ["1927-01-15"],
        "perforation": {
            "measurements": ["12"],
            "method": "comb perf"
        },
        "paper": {"type": "wove paper"},
        "printing": {"method": "lithographed"},
        "watermark": {"type": "Crown CA", "position": "inverted"},
        "gum": {"type": "original gum"},
        "condition": {
            "mint_status": "MNH",
            "centering": "very fine",
            "defects": []
        },
        "varieties": [
            {
                "class": "overprint",
                "subtype": "inverted", 
                "label": "sobrecarga invertida",
                "confidence": 0.8
            }
        ],
        "costa_rica_context": {
            "guanacaste_period": true,
            "personalities": ["Jesús Jiménez"],
            "geographic_features": ["Volcán Arenal"]
        }
    },
    "topics": {
        "primary": "aviacion",
        "secondary": ["overprint", "perforation"],
        "tags": ["variety", "error"],
        "confidence": 0.95
    },
    "axes": {
        "type": ["airmail", "commemorative"],
        "period": ["1920s"]
    },
    "quality_score": 0.87
}
```

## 🎯 Casos de Uso para Investigación Filatélica

### 1. **Búsquedas por Catálogo**
```python
# Encontrar todas las estampillas Scott C1-C10
filters = {"scott_numbers": {"operator": "in", "valueStringArray": ["C1", "C2", "C3"]}}

# Buscar variedades Michel específicas
filters = {"michel_numbers": {"operator": "Like", "valueString": "247*"}}
```

### 2. **Filtrado por Especificaciones Técnicas**
```python
# Estampillas imperforadas en papel laid
filters = {
    "perforation_type": {"operator": "Equal", "valueString": "imperforate"},
    "paper_type": {"operator": "Equal", "valueString": "laid paper"}
}
```

### 3. **Investigación de Variedades**
```python
# Errores de color con alta confianza
filters = {
    "has_errors": {"operator": "Equal", "valueBoolean": true},
    "variety_classes": {"operator": "ContainsAny", "valueStringArray": ["color_error"]},
    "confidence": {"operator": "GreaterThan", "valueNumber": 0.8}
}
```

### 4. **Contexto Histórico Costa Rica**
```python
# Período Guanacaste con personalidades específicas
filters = {
    "is_guanacaste": {"operator": "Equal", "valueBoolean": true},
    "cr_personalities": {"operator": "ContainsAny", "valueStringArray": ["Jesús Jiménez"]}
}
```

## 📊 Métricas de Calidad

El sistema implementa un scoring automático basado en:

- **Identificación de Catálogo** (0.3): Presencia y cantidad de números de catálogo
- **Información Temporal** (0.1): Fechas de emisión precisas
- **Especificaciones Técnicas** (0.2): Perforación, papel, impresión, etc.
- **Clasificación de Variedades** (0.1): Detección de EFO
- **Contexto Temático** (0.1): Clasificación por temas
- **Información Regional** (0.2): Contexto específico Costa Rica

**Rangos de Calidad:**
- 0.80-1.00: Alta calidad (investigación profesional)
- 0.60-0.79: Calidad media (uso general)
- 0.00-0.59: Calidad básica (requiere revisión)

## 🚀 Resultados de Pruebas

### Sistemas de Catálogos: ✅ 100%
- Scott: 15/15 variaciones reconocidas
- Michel: 3/3 patrones correctos
- Yvert: 3/3 formatos identificados  
- Zumstein: 2/2 casos exitosos
- Gibbons: 3/3 variantes detectadas

### Especificaciones Técnicas: ✅ 95%
- Perforación: Detección correcta de medidas y tipos
- Papel: Identificación precisa de características
- Marca de Agua: Reconocimiento de tipos y posiciones
- Impresión: Clasificación exacta de métodos
- Goma: Evaluación completa de condiciones

### Clasificación EFO: ✅ 90%
- Sobrecargas invertidas: Detección perfecta
- Errores de color: 85% de precisión
- Impresiones espejo: Identificación correcta
- Scoring de confianza: Algoritmo calibrado

### Contexto Costa Rica: ✅ 95%
- Período Guanacaste: Reconocimiento automático
- Personalidades: Detección multilingual
- Geografía: Identificación de características

## 🔮 Roadmap y Mejoras Futuras

### Versión 3.1 (Próxima)
- [ ] Integración con APIs de precios (Colnect, StampWorld)
- [ ] Reconocimiento de imágenes con ML
- [ ] Validación cruzada entre catálogos
- [ ] Expansión a otros países centroamericanos

### Versión 3.2 
- [ ] Análisis de tendencias de mercado
- [ ] Detección automática de falsificaciones
- [ ] Sistema de recomendaciones para coleccionistas
- [ ] API REST completa

## 📚 Referencias y Fuentes

1. **Scott Publishing Company**: Standard Postage Stamp Catalogue
2. **Michel Rundschau**: Briefmarken Katalog
3. **Yvert & Tellier**: Catalogue Mondial de Cotation
4. **Stanley Gibbons**: Stamp Catalogue
5. **Philatelic Foundation**: Authentication and Expertise
6. **Costa Rica Postal History**: FESOFILCA Research

---

**Desarrollado con ❤️ para la investigación filatélica avanzada**  
*Sistema integrado con Weaviate vector database para máximo rendimiento*