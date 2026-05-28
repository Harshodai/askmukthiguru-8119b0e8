# Chapter 6: Chapter 5  

## Core Idea  
This chapter teaches how to structure prompts effectively for large language models (LLMs) by combining static content, dynamic context, retrieval-augmented generation (RAG), and summarization techniques. It emphasizes the importance of organizing prompts into coherent sections and leveraging external data sources like RAG to enhance recommendations.

## Frameworks Introduced  
1. **Static Content**: Used to define problems or provide examples for LLMs.  
   - When to use: When you need a clear problem statement or reference material.
   - How: Include in the prompt as boilerplate, examples, or context.

2. **Dynamic Context**: Represents user-specific information and current context.  
   - When to use: For tailored recommendations based on user behavior or preferences.
   - How: Use chunking strategies like Focused, Incremental, or Background to organize content.

3. **Retrieval-Augmented Generation (RAG)**: Combines LLMs with retrieval systems for external data.  
   - When to use: When you need context from external sources without overwhelming the model.
   - How: Index documents and query embeddings for efficient similarity search.

4. **Lexical Retrieval**: Matches text based on word or phrase occurrences.  
   - When to use: For exact matches in static content.
   - How: Convert text into embeddings and search vector databases.

5. **Hierarchical Summarization**: Breaks down information into multi-level summaries.  
   - When to use: For complex texts with natural hierarchies (e.g., chapters in books).
   - How: Summarize at different levels of granularity.

## Key Concepts  
- **Static Content**: Boilerplate or examples that define the problem or guide generation.  
- **Dynamic Context**: User-specific information organized into meaningful chunks.  
- **RAG**: Enhances prompts with external data through efficient retrieval and generation.  
- **Lexical Retrieval**: Exact matches in static content, useful for structured data.  
- **Hierarchical Summarization**: Reduces complexity by breaking down texts into summaries.

## Mental Models  
- Use RAG when you need to enhance recommendations with external context.
- Apply lexical retrieval for exact matches in static prompts.
- Implement hierarchical summarization for complex texts.

## Anti-patterns  
1. Overloading prompts with irrelevant information.  
2. Lack of organization, leading to confusion or distraction.  
3. Misunderstanding relevance in retrieval systems, causing incorrect associations.

## Code Examples  
```python
import numpy as np
from openai import OpenAI

def get_embedding(text):
    text = text.replace("\n", " ")
    return client.embeddings.create(
        input=[text], 
        model="text-embedding-3-small",
    ).data[0].embedding

def index_reviews(reviews):
    # Get the embeddings for all reviews
    vectors = []
    for review in reviews:
        vectors.append(get_embedding(review))
    # Create the vector space model (e.g., FAISS)
    d = len(vectors[0])  # Dimension of the embeddings
    index = faiss.IndexFlatL2(d)
    # Reshape vectors into 2D array and add to the index
    vectors = np.array(vectors).reshape(len(reviews), -1)
    index.add(vectors)
    return index

def retrieve_reviews(index, query, reviews, k=2):
    # Get the embedding for the query text
    query_vector = get_embedding(query)
    # Search the index for the nearest neighbors
    distances, indices = index.search(query_vector, k)
    # Gather the relevant reviews from the indexed texts
    return [reviews[i] for i in indices[0]]

index = index_reviews(reviews)
book = "The Beach by Alex Garland critiques backpacking culture"
related_reviews = retrieve_reviews(index, book, reviews)
```

This code demonstrates how to use OpenAI's embedding model to create a simple RAG application. It indexes reviews and retrieves the most relevant ones for a given query.

## Reference Tables  
| Framework                | Application                                      |
|--------------------------|----------------------------------------------------|
| Static Content          | Defining problems or providing examples             |
| Dynamic Context         | Tailoring recommendations based on user context     |
| Retrieval-Augmented Generation (RAG) | Enhancing prompts with external data                 |
| Lexical Retrieval         | Exact matches in static content                      |
| Hierarchical Summarization | Reducing complexity by breaking down texts          |

## Key Takeaways  
1. Structure prompts with static content upfront to guide LLMs.  
2. Use retrieval methods like FAISS for efficient context enhancement.  
3. Apply summarization techniques to simplify complex texts.  
4. Avoid overloading prompts with irrelevant information.  

## Connects To  
- Chapter 5: Discusses chunking strategies and retrieval systems.  
- Chapter 7: Explores advanced prompt engineering techniques.