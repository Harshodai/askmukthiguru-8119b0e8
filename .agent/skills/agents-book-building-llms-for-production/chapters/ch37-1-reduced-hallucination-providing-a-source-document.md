# Chapter 37: Reduced Hallucination : Providing a source document

## Core Idea
The chapter focuses on minimizing hallucinations in AI outputs by providing structured, reliable source documents. It emphasizes using precise and relevant information to enhance the accuracy of large language model (LLM) responses.

## Frameworks Introduced
- **CharacterTextSplitter**: A method for splitting text into chunks based on character sequences, ensuring manageable segments while preserving context.
  - When to use: When dealing with structured or semi-structured texts that can be divided by specific characters like newlines or spaces.
  - How: Splits text using predefined characters and adjusts chunk size and overlap as needed.

## Key Concepts
- **Source Document**: A primary input providing factual information, used to generate accurate AI outputs.
- **Chunk Size**: The maximum length of each segment in characters.
- **Chunk Overlap**: The number of overlapping characters between consecutive chunks.

## Mental Models
- Use CharacterTextSplitter when you need structured text segments with controlled hallucination risk.
- Think of RecursiveCharacterTextSplitter as a more advanced tool for handling complex texts by adjusting splitting criteria dynamically.

## Anti-patterns
- **Overlapping Chunks**: Redundant or excessive overlap can lead to information duplication and increased hallucination risk.
- **Fixed Chunk Size Without Context**: Using fixed chunk sizes without considering the text's inherent structure may result in irrelevant or incomplete segments.

## Code Examples
```python
from langchain.text_splitter import CharacterTextSplitter

text = "This is a sample text with arbitrary chunks of 100 characters, overlapping by 20."
splitter = CharacterTextSplitter(chunk_size=100, chunk_overlap=20)
chunks = splitter.split_documents([text])

for chunk in chunks:
    print(f"Chunk: {chunk.page_content}")
```

## Reference Tables
| Parameter          | Description                          | Default Value |
|--------------------|---------------------------------------|---------------|
| `chunk_size`       | Maximum length of each segment (chars)| 1000          |
| `chunk_overlap`    | Number of overlapping characters      | 20            |

## Key Takeaways
1. Use CharacterTextSplitter to manage hallucination risk by providing structured, relevant chunks.
2. Adjust chunk size and overlap based on the text's complexity and domain-specific needs.

## Connects To
- Relates to document loading techniques (e.g., PyPDFLoader) for handling structured texts efficiently.