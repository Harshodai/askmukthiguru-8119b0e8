# Chapter 4: Building a research summarization engine

## Core Idea
The chapter teaches how to create an automated research summarization engine using LangChain's tools, combining web searches and document chunking to efficiently summarize large bodies of text.

## Frameworks Introduced
- **Summarization Flowchart**: A decision tree guiding the choice between splitting, MapReduce, or refine techniques based on context window size.
  - When to use: For single documents fitting in a context window or multiple unrelated documents.
  - How: Use "stuff" for small texts; MapReduce for large documents exceeding context limits; Refine for combining summaries iteratively.

- **MapReduce**: Handles large texts by splitting into chunks, summarizing each with an LLM, then combining results.
  - When to use: For documents too long for a single context window.
  - How: Split → map (summarize) → reduce (combine).

- **Refine Technique**: Iteratively updates summaries by incorporating new document chunks sequentially.
  - When to use: For ensuring each document's content is preserved in the final summary.
  - How: Start with initial summary; iteratively refine with additional chunks.

## Key Concepts
- **TextSplitter**: Splits text into manageable chunks for summarization, using a context window limit.
- **TokenTextSplitter**: Splits based on token count to control costs and efficiency.
- **Summarizer**: An LLM model trained to generate concise summaries from prompts.
- **MapReduce Chain**: Combines map (chunk summarization) with reduce (combining results).
- **Refine Chain**: Iteratively refines summaries by incorporating new document chunks.

## Mental Models
Use MapReduce when:
- The input text exceeds the context window limit.
- Parallel processing speed is a priority over summary completeness.

Use Refine when:
- Preserving all contextual information from multiple documents is crucial.
- Sequential processing is acceptable for accuracy.

Avoid splitting documents into too many chunks, as it increases token costs and reduces efficiency.

## Anti-patterns
- **Splitting Too Many Chunks**: Increases token costs and reduces summary quality. Use a reasonable chunk size (e.g., 300 tokens) to balance context and cost.
- **Ignoring Contextual Information**: Refine technique ensures each document's content is preserved in the final summary.

## Code Examples
```python
from langchain_openai import ChatOpenAI
from langchain_text_splitters import (
    TextSplitter,
    TokenTextSplitter,
)
from langchain_core.prompts import PromptTemplate

llm = ChatOpenAI(model_name="gpt-5-nano")

text_splitter = TokenTextSplitter(
    chunk_size=300,
    chunk_overlap=100
)

map_chunk_chain = (
    RunnableLambda(lambda x: "Summarize this text, and include the main details." + str(x)))
  .runnable(lambda x: f"Write a concise summary of the following text, which joins several summaries, and includes the main details.Text: {x}")
  .llm(llm)
  .str_output_parser()
)

summarize_map_chain = map_chunk_chain.map(
    RunnableLambda(lambda x: f"Summary: {x}"),
    chunk_size=300
)

map_reduce_chain = (
    text_splitter.map(summarize_map_chain.map())
    | summarize_map_chain.reduce(
        RunnableParallel(lambda x, y: f"Combine these summaries into a single concise summary.Text: {y}, Previous summaries: {x}")
    )
  ).run()
```

This code demonstrates:
- **TokenTextSplitter**: Splits text into chunks of up to 300 tokens.
- **MapReduce Chain**: Maps each chunk to a summary, then reduces all summaries into one.

## Reference Tables
| Technique          | Context Window Size | Parallel Processing | Preservation of Context |
|--------------------|----------------------|-----------------------|-------------------------|
| MapReduce          | Exceeds context limit | Yes                  | Limited                 |
| Refine             | Smaller chunks       | No                   | High                   |

## Key Takeaways
1. Use MapReduce for large texts exceeding context window limits.
2. Use the refine technique to ensure all document content is preserved in summaries.
3. Split documents into manageable chunks (e.g., 300 tokens) to balance context and cost.

## Connects To
- Text summarization techniques from Chapter 3
- Web search and information retrieval methods