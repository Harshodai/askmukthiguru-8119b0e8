# Chapter 12: Agent Memory and Knowledge

## Core Idea
This chapter explores how agents can store, retrieve, and augment information through memory and knowledge systems. It covers techniques like Retrieval Augmented Generation (RAG), semantic search, document splitting, vector databases, and practical implementations using tools like LangChain.

### Frameworks Introduced
- **Retrieval Augmented Generation (RAG)**: Uses embeddings to convert text into high-dimensional vectors for efficient similarity searching.
  - When to use: When augmenting prompts with context from external documents.
  - How: Load documents, create embeddings, index them in a vector database, and query using prompt semantics.

- **Document Splitting**: Splits documents into manageable chunks for efficient retrieval.
  - When to use: When dealing with long or complex texts that require fine-grained search capabilities.
  - How: Use chunking algorithms like Character Text Splitter from LangChain based on context overlap.

- **Semantic Search**: Utilizes TF-IDF and cosine similarity to retrieve semantically relevant information.
  - When to use: When searching for information based on meaning rather than exact text matches.
  - How: Convert queries into embeddings, index documents with TF-IDF vectors, and perform similarity searches.

### Key Concepts
- **Document Embeddings**: Represents the semantic meaning of documents in vector space, enabling semantic search.
- **Vector Database**: Stores document vectors for efficient similarity searching (e.g., FAISS).
- **RAG Workflows**: Combines retrieval systems with augmentation techniques to enhance AI agent prompts.

### Mental Models
- **Conversational Memory**: Stores recent interactions and enhances prompt semantics in LangChain.
  - Use conversational memory when maintaining context across conversations.
- **Episodic and Semantic Memories**: Store factual information for long-term knowledge recall, implemented using LLMs.
  - Use episodic memories for event-based facts and semantic memories for general knowledge.

### Anti-patterns
- **Excessive Chunking Without Overlap**: Can lead to inefficient retrieval if chunks are too granular or unrelated.
- **Reliance on TF-IDF Only**: May miss nuanced information in documents, leading to incomplete search results.

### Code Examples
```python
from langchain.document_loaders import DirectoryLoader
from langchain.embeddings import OpenAIEmbeddings
from langchain memory_example import DocumentSplitter

loader = DirectoryLoader("sample_documents/mother_goose.html")
data = loader.load()
splitter = DocumentSplitter.from_tiktoken(
    chunk_size=100,
    chunk_overlap=25,    
    length_function=len
)
documents = splitter.split_documents(data, show=True)

embeddings = OpenAIEmbeddings()
doc_search = VectorSearchIndex(embeddings)
```
This code demonstrates:
- Loading documents from a directory.
- Splitting documents into chunks using token-based splitting.
- Creating embeddings and vector search index for efficient retrieval.

### Reference Tables
| Metric                     | Use Case                                      |
|----------------------------|------------------------------------------------|
| TF-IDF score threshold      | For identifying semantically similar documents  |
| Cosine similarity          | For measuring semantic relatedness between texts |

## Key Takeaways
1. Implement RAG workflows to enhance prompts with contextual information.
2. Choose appropriate document splitting strategies based on content complexity.
3. Utilize vector databases for efficient semantic searches.
4. Leverage conversational memory for maintaining AI agent context.

## Connects To
- Retrieval patterns (Chapter 8)
- Knowledge management and retrieval (Chapter 9)