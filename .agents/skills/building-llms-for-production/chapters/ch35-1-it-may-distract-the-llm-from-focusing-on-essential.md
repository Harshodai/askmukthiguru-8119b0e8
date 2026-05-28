# Chapter 35: Enhancing Retrieval Efficiency with Document Compression

## Core Idea
This chapter demonstrates how to enhance retrieval efficiency by compressing documents using a ContextualCompressionRetriever, which ensures only relevant content is returned based on queries.

## Frameworks Introduced
- **ContextualCompressionRetriever**: Combines base_retriever with LLMChainExtractor for efficient document compression.
  - When to use: When dealing with large datasets or multiple documents needing focused retrieval.
  - How: Compresses documents using the context of the query, ensuring only relevant information is returned.

## Key Concepts
- **ContextualCompressionRetriever**: A wrapper that compresses retrieved documents based on query context.
- **LLMChainExtractor**: Uses an LLM to extract relevant content from compressed documents.

## Mental Models
- Use ContextualCompressionRetriever when you need to focus on essential information in large document sets. Think of it as a tool that filters out irrelevant details, allowing the LLM to concentrate on pertinent data.

## Anti-patterns
- **Not compressing or returning full documents**: This can lead to unnecessary data consumption and distraction from key information.

## Code Examples
```python
from langchain.retrievers import ContextualCompressionRetriever  
from langchain.retrievers.document_compressors import LLMChainExtractor  

# Create GPT3 wrapper  
llm = OpenAI(model ="gpt-3.5-turbo" , temperature =0)  

# create compressor for the retriever  
compressor = LLMChainExtractor.from_llm(llm)  
compression_retriever = ContextualCompressionRetriever(  
    base_compressor =compressor,  
    base_retriever =retriever  
)
```
This code demonstrates how to create a compressed retriever using an LLM.

## Reference Tables
| Framework                | Application                                      |
|--------------------------|--------------------------------------------------|
| ContextualCompressionRetriever | Compresses documents based on query context.     |
| LLMChainExtractor        | Extracts relevant content from compressed docs.  |

## Key Takeaways
1. Use ContextualCompressionRetriever when dealing with large document sets to focus on essential information.
2. Understand how to create loaders for different data types (TextLoader, PyPDFLoader, SeleniumURLLoader, GoogleDriveLoader).
3. Always consider the compression ratio and its impact on query relevance.

## Connects To
- Relates to efficient information retrieval strategies in technical writing and AI applications.