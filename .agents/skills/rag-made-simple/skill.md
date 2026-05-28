---
name: rag-made-simple
description: "Knowledge base from 'RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf'. Use when referencing concepts, patterns, or frameworks from this book."
allowed-tools:
  - Read
  - Grep
argument-hint: [topic or chapter number]
---

# RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf

## How to Use This Skill
- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about a specific topic; I find and read the relevant chapter
- **With chapter** — ask for `chXX`; I load that chapter file

---

## Core Frameworks & Mental Models

Here is an organized and comprehensive glossary of key terms from the provided chapters:

- **Copyright** (Ch 1): The legal permission to reproduce or distribute copyrighted works.
  
- **How It Works** (Ch 2): An overview explaining the process and principles behind RAG.

- **When to Use This** (Ch 3): Guidelines on appropriate scenarios for utilizing RAG technology.

- **Quick-Reference Tables** (Ch 4): A concise table listing common tasks with corresponding functions or steps.

- **Simple RAG: The Foundation of** (Ch 5): Introduces the basic technique using TF-IDF weighting for factual queries.

- **Load document and extract raw text** (Ch 6): Describes preprocessing a document to retrieve raw text.

- **RAG for Structured Data** (Ch 7): Focuses on handling semi-structured or unstructured data without predefined schemas.

- **Load CSV file and parse into rows** (Ch 8): Details the process of loading and parsing CSV files.

- **Reliable RAG: Building Trust Through** (Ch 9): Emphasizes AI techniques like TF-IDF, LDA, and BM25 for explainable retrieval.

- **For each retrieved chunk:** (Ch 10) & **Receive generated answer and source documents** (Ch 11): Steps in the retrieval process after initial results are obtained.

- **Proposition Chunking: Breaking down document into initial text chunks** (Ch 12, Ch 13): Methods to split a document into manageable text segments.

- **Query Transformations: Reshaping the query for better retrieval accuracy through keyword expansion and synonym replacement** (Ch 14): Strategies to refine user queries.

- **LLM generates a more specific, detailed version of the query** (Ch 15): Use of large language models to enhance query specificity.

- **Run vector search independently for each sub-query** (Ch 16): Technique for efficient retrieval by processing sub-queries separately.

- **Hypothetical Document Embedding** (Ch 17): Creates hypothetical documents based on embeddings for enhanced retrieval.

- **Receive user question** (Ch 18, 

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-1-copyright.md) | 1. Copyright | Key concepts and frameworks |
| [ch02](chapters/ch02-3-how-it-works.md) | 3. How It Works | Key concepts and frameworks |
| [ch03](chapters/ch03-4-when-to-use-this.md) | 4. When to Use This | Key concepts and frameworks |
| [ch04](chapters/ch04-6-quick-reference-tables.md) | 6. Quick-Reference Tables | Key concepts and frameworks |
| [ch05](chapters/ch05-chapter-1-simple-rag-the-foundation-of.md) | Chapter 1: Simple RAG: The Foundation of | Key concepts and frameworks |
| [ch06](chapters/ch06-1-load-document-and-extract-raw-text.md) | 1. Load document and extract raw text | Key concepts and frameworks |
| [ch07](chapters/ch07-chapter-2-rag-for-structured-data-when.md) | Chapter 2: RAG for Structured Data: When | Key concepts and frameworks |
| [ch08](chapters/ch08-1-load-csv-file-and-parse-into-rows.md) | 1. Load CSV file and parse into rows | Key concepts and frameworks |
| [ch09](chapters/ch09-chapter-3-reliable-rag-building-trust-through.md) | Chapter 3: Reliable RAG: Building Trust Through | Key concepts and frameworks |
| [ch10](chapters/ch10-1-for-each-retrieved-chunk.md) | 1. For each retrieved chunk: | Key concepts and frameworks |
| [ch11](chapters/ch11-1-receive-the-generated-answer-and-the-source-documents.md) | 1. Receive the generated answer and the source documents | Key concepts and frameworks |
| [ch12](chapters/ch12-chapter-4-proposition-chunking-breaking.md) | Chapter 4: Proposition Chunking: Breaking | Key concepts and frameworks |
| [ch13](chapters/ch13-1-split-document-into-initial-text-chunks.md) | 1. Split document into initial text chunks | Key concepts and frameworks |
| [ch14](chapters/ch14-chapter-5-query-transformations-reshaping-the.md) | Chapter 5: Query Transformations: Reshaping the | Key concepts and frameworks |
| [ch15](chapters/ch15-3-llm-generates-a-more-specific-detailed-version.md) | 3. LLM generates a more specific, detailed version | Key concepts and frameworks |
| [ch16](chapters/ch16-4-run-vector-search-independently-for-each-sub-query.md) | 4. Run vector search independently for each sub-query | Key concepts and frameworks |
| [ch17](chapters/ch17-chapter-6-hypothetical-document-embedding.md) | Chapter 6: Hypothetical Document Embedding | Key concepts and frameworks |
| [ch18](chapters/ch18-1-receive-user-question.md) | 1. Receive user question | Key concepts and frameworks |
| [ch19](chapters/ch19-chapter-5-explored-three-query-transformation-strategies-rewriting-step.md) | Chapter 5 explored three query transformation strategies: rewriting, step- | Key concepts and frameworks |
| [ch20](chapters/ch20-chapter-7-contextual-chunk-headers-giving.md) | Chapter 7: Contextual Chunk Headers: Giving | Key concepts and frameworks |
| [ch21](chapters/ch21-3-for-each-chunk-prepend-the-title-to-the-chunk-text.md) | 3. For each chunk, prepend the title to the chunk text | Key concepts and frameworks |
| [ch22](chapters/ch22-chapter-8-context-enrichment-window.md) | Chapter 8: Context Enrichment Window | Key concepts and frameworks |
| [ch23](chapters/ch23-1-store-position-metadata-during-chunking.md) | 1. Store Position Metadata During Chunking | Key concepts and frameworks |
| [ch24](chapters/ch24-chapter-7-introduced-contextual-chunk-headers-which-prepend-document.md) | Chapter 7 introduced contextual chunk headers, which prepend document- | Key concepts and frameworks |
| [ch25](chapters/ch25-chapter-9-semantic-chunking-splitting-text.md) | Chapter 9: Semantic Chunking: Splitting Text | Key concepts and frameworks |
| [ch26](chapters/ch26-1-split-document-into-individual-sentences.md) | 1. Split document into individual sentences | Key concepts and frameworks |
| [ch27](chapters/ch27-chapter-10-contextual-compression-extracting.md) | Chapter 10: Contextual Compression: Extracting | Key concepts and frameworks |
| [ch28](chapters/ch28-1-receive-user-query.md) | 1. Receive user query | Key concepts and frameworks |
| [ch29](chapters/ch29-chapter-11-document-augmentation-giving-every.md) | Chapter 11: Document Augmentation: Giving Every | Key concepts and frameworks |
| [ch30](chapters/ch30-1-split-document-into-chunks.md) | 1. Split document into chunks | Key concepts and frameworks |
| [ch31](chapters/ch31-chapter-12-fusion-retrieval-combining-keyword.md) | Chapter 12: Fusion Retrieval: Combining Keyword | Key concepts and frameworks |
| [ch32](chapters/ch32-1-preparation-chunk-the-document.md) | 1. Preparation: chunk the document | Key concepts and frameworks |
| [ch33](chapters/ch33-chapter-13-reranking.md) | Chapter 13: Reranking | Key concepts and frameworks |
| [ch34](chapters/ch34-2-for-each-candidate-chunk.md) | 2. For each candidate chunk: | Key concepts and frameworks |
| [ch35](chapters/ch35-chapter-14-hierarchical-indices.md) | Chapter 14: Hierarchical Indices | Key concepts and frameworks |
| [ch36](chapters/ch36-1-receive-user-query.md) | 1. Receive user query | Key concepts and frameworks |
| [ch37](chapters/ch37-chapter-15-dartboard-retrieval.md) | Chapter 15: Dartboard Retrieval | Key concepts and frameworks |
| [ch38](chapters/ch38-2-compute-distance-from-query-to-each-candidate.md) | 2. Compute distance from query to each candidate | Key concepts and frameworks |
| [ch39](chapters/ch39-chapter-16-multi-modal-rag-with-captioning.md) | Chapter 16: Multi-Modal RAG with Captioning | Key concepts and frameworks |
| [ch40](chapters/ch40-1-for-each-extracted-image.md) | 1. For each extracted image: | Key concepts and frameworks |
| [ch41](chapters/ch41-chapter-17-retrieval-with-feedback-loops.md) | Chapter 17: Retrieval with Feedback Loops | Key concepts and frameworks |
| [ch42](chapters/ch42-1-receive-new-query.md) | 1. Receive new query | Key concepts and frameworks |
| [ch43](chapters/ch43-chapter-18-adaptive-retrieval.md) | Chapter 18: Adaptive Retrieval | Key concepts and frameworks |
| [ch44](chapters/ch44-1-receive-classified-factual-query.md) | 1. Receive classified factual query | Key concepts and frameworks |
| [ch45](chapters/ch45-1-receive-query.md) | 1. Receive query | Key concepts and frameworks |
| [ch46](chapters/ch46-chapter-19-explainable-retrieval.md) | Chapter 19: Explainable Retrieval | Key concepts and frameworks |
| [ch47](chapters/ch47-1-receive-user-query.md) | 1. Receive user query | Key concepts and frameworks |
| [ch48](chapters/ch48-chapter-20-corrective-rag.md) | Chapter 20: Corrective RAG | Key concepts and frameworks |
| [ch49](chapters/ch49-1-retrieve-top-k-documents-from-vector-store.md) | 1. Retrieve top-K documents from vector store | Key concepts and frameworks |
| [ch50](chapters/ch50-chapter-21-graph-rag.md) | Chapter 21: Graph RAG | Key concepts and frameworks |
| [ch51](chapters/ch51-1-split-documents-into-text-chunks.md) | 1. Split documents into text chunks | Key concepts and frameworks |
| [ch52](chapters/ch52-chapter-22-rag-evaluation.md) | Chapter 22: RAG Evaluation | Key concepts and frameworks |
| [ch53](chapters/ch53-1-receive-the-generated-answer-and-the-retrieved-context.md) | 1. Receive the generated answer and the retrieved context | Key concepts and frameworks |

## Supporting Files
- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides
