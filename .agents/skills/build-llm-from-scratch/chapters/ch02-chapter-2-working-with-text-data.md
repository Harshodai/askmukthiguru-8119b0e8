# Chapter 2: Working with text data

## Core Idea
The chapter teaches how to convert raw text into numerical representations (embeddings) suitable for training large language models (LLMs). This involves tokenization, encoding tokens into IDs, creating input windows with padding and stride, and generating embeddings that capture both word-level and positional information.

## Frameworks Introduced
- **GPT-like decoder-only transformer architecture**: Used for text generation tasks.
  - When to use: For general-purpose text processing and generation.
  - How: Tokenize text into subwords or words, convert to IDs with padding, create input windows with stride, generate embeddings, and pass through the transformer.

## Key Concepts
- **Text Processing Pipeline**: The process of converting raw text into numerical representations for model training.  
- **Tokenization**: Breaking text into tokens (words or subwords) using BPE tokenizer.
- **Token IDs**: Unique integers assigned to each token in a vocabulary.
- **Embedding Layer**: A lookup table that converts token IDs into dense vector representations.
- **Positional Embeddings**: Add positional information to embeddings for models to understand word order.

## Mental Models
- Use GPT-like models when working with text data.  
  - Think of it as a system that processes sequential text and generates meaningful outputs like translations or completions.

## Anti-patterns
- Ignore tokenization steps and treat raw strings as input.
  - Avoid this to ensure consistent numerical representations for model training.
- Do not pad or stride inputs arbitrarily without understanding the impact on sequence length and model performance.
  - This can lead to inefficient training and overfitting due to mismatched sequence lengths.

## Code Examples
```
class GPTDataset(Dataset):
    def __init__(self, text, tokenizer, max_length, stride=128):
        self.input_ids = []
        self.target_ids = []
        token_ids = tokenizer.encode(text)
        for i in range(0, len(token_ids) - max_length, stride):
            input_tokens = token_ids[i:i + max_length]
            target_tokens = token_ids[i + 1:i + max_length + 1]
            self.input_ids.append(torch.tensor(input_tokens))
            self.target_ids.append(torch.tensor(target_tokens))

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, idx):
        input_ids = self.input_ids[idx]
        target_ids = self.target_ids[idx]
        return input_ids, target_ids

class TokenEmbedding:
    def __init__(self, vocab_size, output_dim):
        self.embedding_layer = torch.nn.Embedding(vocab_size, output_dim)
    
    def get_embedding(self, token_ids):
        return self.embedding_layer(torch.tensor([token_ids]))
```

## Reference Tables
| **Term**                  | **Definition**                                                                 |
|---------------------------|-----------------------------------------------------------------------------|
| Tokenization               | Process of breaking text into tokens (words or subwords) for numerical representation. |
| BPE Tokenizer              | A method to split text into subword units, creating a new vocabulary and token IDs. |
| Embedding Layer            | A lookup table that converts token IDs into dense vector representations. |

## Key Takeaways
1. Process raw text through tokenization, encoding, padding, and embedding steps.
2. Use GPT-like models for tasks like text generation by converting text to numerical representations.
3. Implement positional embeddings to capture word order in sequences.
4. Handle unknown words with special tokens (e.g., `<unk>`) and ensure consistent vocabulary across different inputs.

## Connects To
- The next chapter will focus on implementing attention mechanisms, which are fundamental for LLMs like GPT.