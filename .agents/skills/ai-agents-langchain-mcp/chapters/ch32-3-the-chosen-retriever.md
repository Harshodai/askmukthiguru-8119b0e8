# Chapter 32: The chosen retriever

## Core Idea
This chapter teaches how to route questions to appropriate data sources using machine learning models, ensuring accurate and relevant responses by leveraging LLMs for question analysis and retrieval systems.

## Frameworks Introduced
- **Vector Store Retrieval**: Uses vector stores for general tourist information queries.
  - When to use: For questions about UK destinations or general tourist information.
  - How: Implements a retriever chain with configurable search parameters.
  
- **UK Booking Database Retrieval**: Specialized for accommodation-related queries.
  - When to use: For questions about hotels, bookings, or accommodation availability in the UK.
  - How: Uses a structured database and metadata query system.

## Key Concepts
- **Vector Store**: A database that stores embeddings of documents for efficient similarity searches. Example: `tourist_info_store`.
- **LLM (Large Language Model)**: An AI model used for question routing and answer synthesis. Example: `llm`.
- **Retriever Chain**: A sequence of components that route questions to the appropriate data source. Example: `tourist_info_retriever_chain` or `uk_accommodation_retriever_chain`.

## Mental Models
- Use **LLM-based Routing** when you need to determine the best data source for a question. Think of it as analyzing the intent behind the query and selecting the most suitable retriever based on that intent.

## Anti-patterns
- **Don’t use similarity postprocessing**: This can lead to irrelevant results being included in the response, reducing accuracy.

## Code Examples
```python
# Example code for retrieving data from a vector store
tourist_info_retriever_chain = RunnableLambda(
    lambda x: x['question']
) | llm.with_structured_output(
    RouteQuery) system calls and parameters are configured to handle specific types of queries.
```

This demonstrates how to create a retriever chain that routes questions to the appropriate data source based on intent.

## Reference Tables
| Framework                | When to Use                     |
|-------------------------|---------------------------------|
| Vector Store Retrieval   | General tourist information     |
| UK Booking Database      | Accommodation-related queries    |

## Key Takeaways
1. Use LLMs for routing questions to the appropriate data source based on intent.
2. Implement similarity postprocessing to refine retrieval results.
3. Configure retriever chains with specific search parameters for different query types.

## Connects To
- Chapter 9: Query Generation and Routing
- Chapter 10: Retrieval Postprocessing