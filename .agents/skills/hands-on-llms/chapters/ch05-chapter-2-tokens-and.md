# Chapter 5: Tokens and Embeddings

## Core Idea
Understanding tokens and embeddings is essential for building language models. Tokens break text into manageable pieces (words, subwords), while embeddings convert these tokens into numeric representations for the model to process.

## Frameworks Introduced
- **Word2Vec**: A method that learns word embeddings by predicting surrounding words.
  - When to use: For creating dense vector representations of words based on their co-occurrence in text.
  - How: Trains a neural network to predict context words given a target word or vice versa.

## Key Concepts
- **Tokenization**: The process of splitting text into tokens (words, subwords).
- **Embeddings**: Numeric representations of tokens that capture semantic meaning.
- **Special Tokens**: Tokens like `<s>`, `[PAD]`, and `[UNK]` used for model inputs and outputs.

## Mental Models
- Use Word2Vec when you need to represent words in a high-dimensional vector space. Think of it as capturing the essence of words through their context.
- Avoid using character-level tokenization because it creates sparse, hard-to-model representations.

## Anti-patterns
- **Avoid mixing tokenizers**: Using different tokenization methods for the same model can lead to inconsistencies and errors.
- **Do not use character-level tokens**: They make training complex and less efficient compared to subword tokenization.

## Code Examples
```python
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct")
print(tokenizer.decode(1))  # Outputs: `<s>`
print(tokenizer.decode([102]))  # Outputs: Write
```

## Reference Tables
| Tokenization Method | Vocabulary Size | Training Dataset | Example Subword |
|----------------------|------------------|-------------------|-----------------|
| WordPiece            | ~30k             | Multilingual       | apol-o-r-...     |
| BPE                   | ~40k             | Monolingual        | w-or-k-...       |
| Character-Level       | 52               | Multilingual       | individual chars |

## Key Takeaways
1. Tokens are the building blocks of language models, breaking text into manageable pieces.
2. Subword tokenization (WordPiece/BPE) is preferred for better generalization and modeling efficiency.
3. Special tokens are crucial for model inputs and outputs.

## Connects To
- Relates to Chapter 1 on historical context of LLMs.
- Connects to embeddings discussed in Chapter 4, which are essential for processing tokens.