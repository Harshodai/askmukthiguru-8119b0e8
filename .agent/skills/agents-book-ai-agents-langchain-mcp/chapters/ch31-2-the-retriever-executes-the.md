# Chapter 31: 2. The retriever executes the

## Core Idea
The chapter explains how RAG architectures branch into multiple pathways based on task specificity, with each branch optimized for specific types of queries or tasks.

## Frameworks Introduced
- **SPARQL**: A query language used to retrieve data from a knowledge graph.
  - When to use: For querying structured data in a knowledge graph.
  - How: Used by the SPARQL generator to create retrieval prompts.

- **LLM (Large Language Model)**: Used for synthesizing completions and generating prompts.
  - When to use: For processing user questions and retrieving relevant context.
  - How: The LLM generates responses based on prompts created from user questions and retrieved data.

## Key Concepts
- **Vector DB**: A database optimized for storing and querying unstructured text or numerical data.
- **Relational Database**: A database organized into one or more tables, with rows and columns used to store data.
- **Knowledge Graph DB**: A database that represents real-world entities and their relationships using nodes and edges.

## Mental Models
- Use SPARQL when you need to query structured data from a knowledge graph.  
  - Think of SPARQL as a tool for extracting specific information from a knowledge graph by defining the relationships between entities.

## Anti-patterns
- **Monolithic RAG Architecture**: Avoid creating a single, flat architecture that doesn't branch into specialized pathways.
  - Why it fails: It limits flexibility and scalability when handling diverse tasks or data types.

## Code Examples
```python
# Example of prompt engineering in code
user_question = "Where are the best tourist destinations in Brazil?"
prompt = f"User question: {user_question}\nRetrieve relevant information from a vector store about Brazilian tourist destinations."
```

- **What it demonstrates**: This code snippet shows how to engineer a prompt for retrieving specific information using a vector store.

## Reference Tables
| Storage Type       | Use Case                          |
|--------------------|------------------------------------|
| Vector DB         | Storing unstructured text or numerical data for similarity search. |
| Relational Database| Storing structured data in tables for relational queries.     |
| Knowledge Graph DB| Representing real-world entities and their relationships. |

## Key Takeaways
1. Use SPARQL when you need to query structured data from a knowledge graph.
2. Optimize RAG architectures by branching into specialized pathways based on task specificity.
3. Engineer prompts effectively to retrieve relevant context for specific tasks.

## Connects To
- Relates to the concept of prompt engineering and database types in Chapter 10: "Chain routing"