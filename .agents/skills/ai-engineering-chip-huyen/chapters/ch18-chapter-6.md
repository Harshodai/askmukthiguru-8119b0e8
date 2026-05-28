# Chapter 18: CHAPTER 6

## Core Idea
RAG (Retrieval-Augmented Generation) enhances AI models by augmenting their generation with retrieved information from external sources, enabling them to address tasks more effectively by leveraging context.

## Frameworks Introduced
- **Lewis et al.'s RAG**: A technique that combines retrieval and generation for knowledge-intensive tasks.
  - When to use: For tasks requiring access to external information beyond the model's internal capabilities.
  - How: Retrieving relevant data from external sources (e.g., documents, web pages) and incorporating it into the model's generation process.

- **Anthropic's Agent Framework**: A broader approach that includes tools like web search for automation and interaction with external systems.
  - When to use: For tasks requiring direct interaction with external world elements or automating complex processes.
  - How: Using tools such as web search APIs, news APIs, or other external services to gather information.

## Key Concepts
- **RAG**: Enhances model generation by retrieving relevant information from external sources and integrating it into the model's output.
- **Agents**: Systems that use tools like web search, news APIs, or databases to automate tasks and interact with the world.
- **External Memory**: Data sources beyond the model's internal memory, such as documents, web pages, or external databases.
- **Retriever**: A component of RAG systems responsible for indexing and querying external data sources.
- **Generator**: A component of RAG systems responsible for processing retrieved information and generating a response.
- **TF-IDF (Term Frequency-Inverse Document Frequency)**: A metric combining term frequency and inverse document frequency to score relevance in retrieval algorithms.
- **Elasticsearch**: An inverted index-based search engine used for fast retrieval of documents based on terms.
- **BM25**: A probabilistic ranking algorithm that improves upon TF-IDF for text retrieval, normalizing term frequencies by document length.

## Mental Models
- Use RAG when your model lacks context and needs external information to improve its output.  
  - Think of RAG as a method for augmenting models with external knowledge to enhance their capabilities in specific tasks.

- Use agents (e.g., web search tools) when you need direct interaction with the external world or automate complex processes that require human expertise.

## Anti-patterns
- **Not using RAG or agents when a simpler solution exists**: Over-reliance on tools without considering alternative solutions can lead to inefficiencies.
- **Over-relying on tools without understanding their limitations**: Tools like web search APIs may not always provide the necessary context for specific tasks, leading to incomplete or incorrect results.

## Code Examples
```
# Example code snippet from Lewis et al.'s RAG paper
from typing import Tuple

def get_relevant_documents(query: str, retriever: Retrieval, top_k: int = 5) -> list:
    """
    Retrieves the most relevant documents for a given query using a retrieval system.
    
    Args:
        query (str): The search query to retrieve documents for.
        retriever (Retrieval): The retrieval component that indexes and queries external data sources.
        top_k (int): The number of top documents to return. Defaults to 5.
        
    Returns:
        list: A list of the most relevant documents retrieved from external sources.
    """
    indexed_documents = retriever.retrieve_all()
    scores = retriever scoring indexed_documents using TF-IDF
    sorted_documents = sorted(indexed_documents, key=lambda x: scores[x], reverse=True)
    return sorted_documents[:top_k]
```

This code demonstrates how to retrieve relevant documents for a query by combining retrieval and ranking mechanisms.

## Reference Tables

| Retrieval Algorithm | Type          | Description                                      |
|----------------------|---------------|-------------------------------------------------|
| Term-based Retrieval  | Supervised   | Uses keyword matching and term frequency-IDF    |
| Embedding-Based      | Unsupervised | Relies on dense vector representations           |
| BM25                 | Modified TF-IDF| Improves upon TF-IDF with normalization         |

## Key Takeaways
1. RAG is a powerful technique for enhancing model capabilities by augmenting generation with external context.
2. Agents provide a broader framework for automating tasks and interacting with the external world, complementing RAG's strengths.
3. Context management is crucial for effective AI applications, balancing the need for external information with efficient indexing strategies.

## Connects To
- Information Retrieval: The chapter builds on traditional retrieval systems like Elasticsearch and BM25 while introducing advanced techniques like TF-IDF scoring.
- NLP: The concepts of RAG are deeply rooted in natural language processing and information retrieval principles.