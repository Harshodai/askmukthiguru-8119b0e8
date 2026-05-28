```markdown
# Chapter 8: Knowledge and Memory

## Core Idea
Knowledge and memory in agentic systems extend beyond context windows by incorporating retrieval-augmented generation (RAG) with semantic memory, enabling agents to reason over external knowledge and adaptively retrieve relevant information.

## Frameworks Introduced
- **BM25Okapi**: A ranking function for keyword-based search using TF-IDF scoring.  
  - When to use: For exact keyword matching in large text corpora.
  - How: Implements the BM25 algorithm with configurable parameters like window size and overlap.

- **GraphRAG**: An advanced RAG system that uses knowledge graphs to store structured data for multihop reasoning.  
  - When to use: For complex tasks requiring interconnected data relationships.
  - How: Combines retrieval from a graph database with generative models to produce contextually rich responses.

## Key Concepts
- **BM25 Scoring Function**: A ranking algorithm that measures the relevance of documents to a query based on term frequency, inverse document frequency, and document length normalization.  
- **Vector Store**: A data structure for storing high-dimensional vector representations of text, enabling efficient similarity searches.  
- **Knowledge Graph**: A graph-based representation of entities (nodes) and their relationships (edges), used for structured reasoning.

## Mental Models
- Use BM25 when you need exact keyword matches in a large text corpus.
- Think of BM25 as a tool for retrieving precise, relevant information based on query terms.  
- Use GraphRAG when you need to reason over interconnected data for complex tasks.

## Anti-patterns
- **Over-reliance on context windows**: Can lead to information loss and failure to generalize across sessions.
  - Why it fails: Context windows discard outdated information too quickly, limiting the agent's ability to learn and adapt.

## Code Examples
```python
# Example of BM25 setup using rank_bm25
from rank_bm25 import BM25Okapi

corpus = ["Document 1 text", "Document 2 text"]
bm25 = BM25Okapi(corpus)
query = "search query"
results = bm25.get_top_n(query, corpus, n=3)

# Example of knowledge graph construction
from typing import Annotated
from typing_extensions import TypedDict

class Node(TypedDict):
    id: str
    label: str
    content: str

nodes: List[Node] = [
    {"id": "1", "label": "Person", "content": "Alice"},
    {"id": "2", "label": "Company", "content": "Tech Corp"}
]

edges: List[TypedDict] = [
    {"from": "1", "to": "2", "label": "Affiliation", "content": "Alice works at Tech Corp"}
]
```

## Reference Tables
| Framework       | Use Case                          | Pros                                  | Cons                              |
|-----------------|------------------------------------|---------------------------------------|-----------------------------------|
| BM25Okapi       | Exact keyword matching in text      | Fast, scalable for large corpora        | Limited to exact matches only      |
| GraphRAG        | Complex reasoning over interconnected data | Handles multihop queries and relationships | Requires setup effort               |

## Key Takeaways
1. Use BM25Okapi for precise keyword-based retrieval tasks.
2. Leverage knowledge graphs with GraphRAG for complex, context-aware reasoning.
3. Always balance between relying on external knowledge and maintaining a robust context window.

## Connects To
- Context Engineering (Chapter 6)
- LangGraph Architecture (Chapter 1)
```