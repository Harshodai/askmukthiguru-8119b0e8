# Chapter 28: 3. The retriever searches for

## Core Idea
Query transformations are essential for enhancing retrieval accuracy in vector store search systems by refining user questions, improving context relevance, and enabling more precise answer synthesis.

### Frameworks Introduced
- **Rewrite-Retrieve-Read (R-R-E) Workflow**: A three-step process that involves rewording the query to better align with the vector store's content, retrieving relevant chunks, and synthesizing a comprehensive answer.
  - When to use: When dealing with complex or ambiguous user questions.
  - How: 
    1. Rewrite the original question using domain-specific language or an automated query rewriter.
    2. Retrieve context from the vector store based on the rewritten query.
    3. Synthesize a response by combining the original question and retrieved context.

- **Multi-Query Generation (MQG)**: A technique that generates multiple variations of a user question to retrieve diverse contexts for accurate answer synthesis.
  - When to use: When handling ambiguous or multi-grained questions requiring granular information.
  - How:
    1. Use a prompt template to generate multiple explicit, independent questions from the original query.
    2. Execute each generated question in the vector store to gather distinct context chunks.
    3. Combine all retrieved contexts with the original question to synthesize a comprehensive answer.

- **Step-Back Questioning**: A retrieval enhancement technique that generates a broader, more abstract question before refining it for targeted retrieval.
  - When to use: When initial queries are too narrow or lack context.
  - How:
    1. Generate a less specific but broader question from the original query.
    2. Retrieve context using the step-back question.
    3. Use both the detailed and abstract contexts to inform the final answer synthesis.

- **Hypothetical Document Embeddings (HyDE)**: A technique that generates hypothetical documents based on user intent, improving retrieval by aligning generated content with vector store embeddings.
  - When to use: When enhancing retrieval accuracy through context generation.
  - How:
    1. Use a prompt template to generate a hypothetical document that could answer the user's question.
    2. Embed and retrieve this document alongside the original query.
    3. Use the retrieved hypothetical documents to refine the final answer.

### Key Concepts
- **Query Rewriting**: The process of rephrasing or modifying a user question to better match the vector store's content.
  - Example: "Tell me more about Cornwall" → "What are the key features of Cornwall?"
  
- **Context Retrieval**: The act of fetching relevant information from a vector store based on a query.
  - Example: Retrieving Cornwall-related chunks like Newquay, St Ives, and Tintagel.

- **Multi-Query Generation (MQG)**: Generating multiple explicit questions to retrieve diverse contexts for accurate answers.
  - Example: Turning "What are the best beaches in Cornwall?" into "What are some general tips for a trip to Brighton?"

- **Step-Back Questioning**: Creating a broader question before refining it for targeted retrieval.
  - Example: Changing "What should I know about Cornwall's sea shore paths?" to "What is the general knowledge about Cornwall?"

### Mental Models
Use X when Y:
- Use Multi-Query Generation (MQG) when your initial query is ambiguous or requires granular information.
- Use Hypothetical Document Embeddings (HyDE) when you need to enhance retrieval accuracy through context generation.

### Anti-Patterns
- **Poorly Worded Initial Queries**: Leading to irrelevant or incomplete results.
  - What to avoid: Overly vague or ambiguous questions that fail to elicit useful information.
  
- **Over-Reliance on Single-Step Decomposition**: Ignoring interdependencies between questions.
  - What to avoid: Failing to account for dependencies between questions when decomposing complex queries.

### Code Examples
```python
from langchain_openai import ChatOpenAI
from langchain_core promoter import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-5")
multi_query_prompt_template = """
You are an AI language model assistant. Your task is to generate multiple variations of the given user question to retrieve diverse contexts for accurate answer synthesis.

Generate 3 different versions of the following question:
Original question: {user_question}

Question 1: [Insert parameter from previous answer]
Question 2: [Insert parameter from previous answer]
Question 3: [Insert parameter from previous answer]

Please ensure that each generated question is distinct and provides unique context for retrieval.
"""
multi_query_chain = multi_query_prompt_template | llm | StrOutputParser()
```

### Reference Tables
| Parameter | Value/Range | Purpose |
|---|---|---|
| Vector Store Type | UK_Granular | Limited to Cornwall-related documents |
| Collection Name | uk_gigular_collection | 18,200 Cornwall beach pages |

| Model Settings | Parameter | Value |
|---|---|---|
| LLM API Key | OPENAI_API_KEY | Your OpenAI API key |
| Temperature | 0.3-0.5 | Controls randomness in responses |

### Key Takeaways
1. **Query Rewriting**: Always refine user questions to better align with vector store content.
2. **Multi-Query Generation (MQG)**: Use for ambiguous or granular information retrieval needs.
3. **Step-Back Questioning**: Enhance retrieval accuracy by generating broader, initial context.
4. **Hypothetical Document Embeddings (HyDE)**: Improve answer relevance through context generation.

## Connects To
- Relates to vector store configuration and LLM model tuning in Chapter 9 on Query Transformations for Vector Store Search.