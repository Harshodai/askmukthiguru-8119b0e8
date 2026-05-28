# Chapter 30: The retriever transforms

## Core Idea
The chapter explores advanced techniques for enhancing search queries through metadata enrichment, vector databases, relational databases with semantic search capabilities, and graph databases. It emphasizes leveraging large language models (LLMs) to generate structured and semantically rich queries, improving retrieval accuracy and relevance.

### Frameworks Introduced
- **Metadata-Enriched Queries**: Uses metadata like source, destination, and region to refine search results.
  - When to use: When dealing with geospatial or location-specific data.
  - How: Adds context to search terms to narrow down results based on specific attributes.

- **Vector Database Search (e.g., pgvector)**: Utilizes embeddings for semantic searches in PostgreSQL.
  - When to use: For high-dimensional data requiring meaning-based retrieval.
  - How: Embeds query terms and joins with database entries using vector similarity.

- **Relational Database Query Generation**: Uses LLMs to generate SQL queries from natural language questions.
  - When to use: For structured databases requiring precise SQL formatting.
  - How: Employs templates, prompts, or embeddings to craft SQL statements tailored to the database schema.

- **Graph Databases with SPARQL Generation**: Leverages LLMs for generating Cypher or SPARQL queries from natural language.
  - When to use: For complex knowledge graphs requiring relationship-based searches.
  - How: Transforms NLP prompts into graph query languages, enabling semantic and relational searches.

### Key Concepts
- **Metadata**: Information about data sources, destinations, and regions used to refine search results.
- **Embeddings**: Vector representations of text that capture semantic meaning for enhanced retrieval.
- **Semantic Search**: Retrieving data based on contextual or partial matching rather than exact keyword matches.
- **Graph Databases**: Data structures using nodes and edges to represent entities and relationships, supporting advanced querying.

### Mental Models
- Use vector embeddings when you need semantic search capabilities.
- Apply metadata first for precise results before considering broader queries.

### Anti-patterns
- Avoid raw text searches without context, as they often yield irrelevant results.
- Steer clear of overly simplistic SQL queries that miss the mark on relevance or specificity.

## Code Examples
```python
from langchain_community.utils import ChatOpenAI
llm = ChatOpenAI(model="gpt-5")
docloader = DocLoader.from_url("https://enwikivoyage.org/wiki/volume_1/")

# Example of metadata-enriched query setup
metadata_retriever = retrievers["metadata-enriched"]
```

This code demonstrates how to set up a metadata-enriched retriever using LangChain, showcasing the integration of external data sources and metadata for enhanced retrieval.

## Reference Tables
| Framework                | Use Case                          | How It Works                     |
|-------------------------|------------------------------------|-----------------------------------|
| Metadata-Enriched Queries| Geospatial or location-specific data| Adds context to search terms         |
| Vector Database Search  | High-dimensional semantic data     | Uses embeddings for vector similarity|
| Relational Database     | Structured databases with SQL       | Generates SQL queries programmatically|
| Graph Database          | Complex knowledge graphs           | Transforms NLP prompts into SPARQL   |

## Key Takeaways
1. Metadata enhances search accuracy by adding contextual information.
2. Vector databases improve retrieval accuracy for semantically rich data.
3. Relational and graph databases expand query capabilities with structured data.
4. LLMs empower dynamic query generation, bridging the gap between natural language and database operations.

## Connects To
- Previous chapters on metadata management and vector search provide foundational knowledge.
- Subsequent chapters on advanced querying techniques build upon these concepts for more sophisticated applications.