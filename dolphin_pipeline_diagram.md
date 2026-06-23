# Diagrama del Pipeline Dolphin Parser

```mermaid
flowchart TD
    A[📄 PDF Input<br/>OXCART02.pdf] --> B[🐬 DOLPHIN Model]
    
    B --> C[📊 Recognition Results]
    C --> |"Page-level elements"| D[📑 Pages with Elements]
    
    D --> E{Element Type}
    
    E --> |title, sec, para| F[📝 Text Elements]
    E --> |tab| G[📋 Table Elements]  
    E --> |fig + cap| H[🖼️ Figure Elements]
    E --> |header, foot| I[📄 Marginalia]
    
    F --> J[Transform to OXCART]
    G --> K[🔄 Table Processing]
    H --> L[🖼️ Figure + Caption Fusion]
    I --> J
    
    K --> |HTML → Markdown/TSV| M[📊 Table Chunks]
    K --> |Row extraction| N[📝 Table Row Sentences]
    
    J --> O[📦 Base OXCART Chunks]
    L --> O
    M --> O
    N --> O
    
    O --> P[🏷️ Philatelic Enrichment]
    
    P --> Q{Pattern Matching}
    
    Q --> |Scott A123, M45| R[📚 Catalog Numbers]
    Q --> |January 15, 1960| S[📅 Normalized Dates]
    Q --> |$5.50, ₡100| T[💰 Prices & Values]
    Q --> |jaguar, airmail| U[🏷️ Topics & Themes]
    Q --> |sobrecarga invertida| V[⚠️ Philatelic Varieties]
    
    R --> W[📋 Enriched Metadata]
    S --> W
    T --> W
    U --> W
    V --> W
    
    W --> X[💾 Final JSON Output<br/>OXCART02.enriched.json]
    
    X --> Y[🔍 RAG-Ready Chunks<br/>for Vector Database]
    
    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style X fill:#e8f5e8
    style Y fill:#fff3e0
    
    classDef processing fill:#f0f4c3
    classDef output fill:#c8e6c8
    
    class P,Q processing
    class W,X,Y output
```

## Detalles del Pipeline

### 1. **Entrada** 
- Archivo PDF (ej: `OXCART02.pdf`)

### 2. **Procesamiento Dolphin**
- Modelo multimodal que analiza layout y contenido
- Genera elementos estructurados con reading order

### 3. **Transformación OXCART**
```mermaid
graph LR
    A[Dolphin Elements] --> B[Text Chunks]
    A --> C[Table Processing]
    A --> D[Figure Fusion]
    
    C --> E[Markdown Table]
    C --> F[Row Sentences]
    
    B --> G[OXCART Format]
    E --> G
    F --> G
    D --> G
```

### 4. **Enriquecimiento Filatélico**
```mermaid
mindmap
  root((Philatelic<br/>Enrichment))
    Catalogs
      Scott Numbers
      Michel (M/A)
      Gibbons
      Sanabria
    Temporal
      Dates (EN/ES)
      Years
      Periods (1960s)
    Economic
      Prices (USD/CRC)
      Postal Values
    Varieties
      Inverted Overprints
      Color Errors
      Mirror Prints
    Topics
      Fauna
      Aviation
      Architecture
      Sports
```

### 5. **Salida para RAG**
- Chunks optimizados con metadatos ricos
- Diferentes tipos: `text`, `table`, `table_row`, `figure`
- Listos para indexación vectorial

## Tipos de Chunks Generados

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| `text` | Párrafos y texto general | Descripciones, artículos |
| `table` | Tablas completas en markdown | Catálogos de sellos |
| `table_row` | Filas como oraciones | "Scott: 123, Year: 1960, Value: $0.05" |
| `figure` | Imágenes con captions | Sellos con descripciones |
| `decree` | Decretos legislativos | Autorizaciones oficiales |
| `auction_result` | Resultados de subastas | Precios realizados |