# Chapter 14: Knowledge Retrieval (RAG)

## Core Idea  
The chapter emphasizes that Retrieval-Augmented Generation (RAG) enhances large language models by integrating external knowledge to provide more accurate, verifiable, and contextually relevant responses.

## Frameworks Introduced  
- **Embeddings**: Represents text as numerical vectors for semantic understanding.  
  - When to use: When working with large text data or needing semantic search.  
  - How: Convert text into high-dimensional vectors using models like BERT or GPT.  

- **Semantic Search (BM25)**: A ranking algorithm that understands the meaning of words.  
  - When to use: For simple, literal searches without keyword overlap.  
  - How: Measures term frequency and context to rank documents based on relevance.

- **Vector Databases**: Stores embeddings for efficient semantic search.  
  - When to use: For fast retrieval of similar vector entries.  
  - How: Indexes vectors with metadata for quick nearest neighbor searches.

- **Chunking**: Breaks large documents into smaller, manageable pieces.  
  - When to use: To handle long texts or maintain document context.  
  - How: Splits documents based on readability or meaning preservation.

- **BM25 Hybrid Search**: Combines keyword and semantic search for robust retrieval.  
  - When to use: For complex queries that require both exact matches and semantic relevance.  
  - How: Balances keyword precision with semantic understanding.

## Key Concepts  
- **Embeddings**: Numerical representations of text for semantic analysis.  
- **Semantic Similarity**: Matches documents based on meaning rather than words.  
- **Vector Database**: A database optimized for storing and querying vectors.  
- **Chunking**: Divides large texts into smaller, meaningful segments.  
- **RAG Pattern**: Integrates external knowledge to enhance LLM responses.  

## Mental Models  
- Use embeddings when working with structured or semantic data.  
- Apply BM25 hybrid search for complex queries that require both precision and context.  
- Leverage vector databases for fast retrieval of similar content.  
- Chunking improves document understanding by preserving context during splits.  

## Anti-patterns  
- Avoid relying solely on static training data, as it limits adaptability.  
- Do not neglect periodic retraining to maintain relevance.  
- Steer clear of single-source knowledge bases that can introduce biases.  
- Refrain from using external tools without addressing their limitations.  

## Code Examples  
```python
# Example: Weaviate Integration with LangChain
from langchain_community.document_loaders import TextLoader 
from langchain_community.embeddings import OpenAIEmbeddings 
from langchain_community.vectorstores import Weaviate 

loader = TextLoader(...)  
documents = loader.load()  
loader.close()  

embeddings = OpenAIEmbeddings()  
vectorstore = Weaviate.from_documents(documents, embeddings)  
retriever = vectorstore.as_retriever()  

# Example: RAG Generation with LLM
from langchain_openai import ChatOpenAI 
llm = ChatOpenAI(...)  
response = retriever.invoke("question") + "\n\n" + llm(...).format(context=response)  
```  
- **What it demonstrates**: Integrating chunking, retrieval, and LLM generation for a complete RAG pipeline.

## Reference Tables  
| Parameter | Value/Decision |  
|----------|---------------|  
| Embedding Dimension | 384 (default)|  
| Similarity Threshold | 0.7 (default)|  
| Vector Distance Threshold | 0.65 (default)|  
| Top-k Retrieval | 5 (default)|  

## Key Takeaways  
1. RAG enhances LLMs by integrating external knowledge for more accurate responses.  
2. Embeddings and vector databases are essential for semantic search.  
3. Chunking improves document understanding and retrieval accuracy.  
4. BM25 hybrid search balances precision and context for complex queries.  

## Connects To  
- Information Retrieval, NLP Tasks, Semantic Search