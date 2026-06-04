# Chapter 3: Coding attention mechanisms

## Core Idea
The chapter introduces attention mechanisms as a fundamental component of neural networks, particularly in transformer-based architectures. It explains how models can dynamically focus on relevant parts of input data through scaled dot product attention, softmax normalization, and multi-head attention mechanisms.

## Frameworks Introduced
- **Self-attention**: Computed using query, key, and value vectors within the same tensor.
  - When to use: For modeling interdependent relationships between data points.
  - How: 
    1. Compute query, key, and value matrices from input embeddings.
    2. Calculate attention scores via scaled dot product.
    3. Apply softmax normalization to obtain attention weights.
    4. Multiply attention weights with values to get context vectors.

- **Scaled Dot Product Attention**: Uses a scaling factor of √d_k to prevent exploding gradients during backpropagation.
  - When to use: For maintaining numerical stability in attention computations.
  - How: Scale the dot product scores before applying softmax.

- **Multi-Head Attention**: Implements multiple attention heads to capture diverse contextual relationships.
  - When to use: For modeling complex dependencies and improving model performance.
  - How: 
    1. Project input data into multiple query/key/value representations.
    2. Compute attention weights for each head separately.
    3. Combine the outputs of all heads to form the final context vector.

- **Causal Attention**: Ensures that models do not attend to future tokens in the input sequence.
  - When to use: In language models where temporal order matters.
  - How: Apply a lower-triangular mask to attention weights during computation.

## Key Concepts
- **Query/Key/Value Matrices**: Intermediate transformations of input embeddings used to compute attention scores.
- **Softmax Function**: Converts raw attention scores into probabilities that sum to one across heads.
- **Multi-Head Attention**: Distributes attention computation across multiple heads to learn diverse contextual representations.
- **Causal Mask**: Prevents future tokens from influencing the present by setting corresponding weights to zero in attention computations.

## Mental Models
- Use multi-head attention when you need to capture multiple types of relationships (e.g., different aspects of visual or text data).
- Apply dropout after attention and feed-forward layers to prevent overfitting.
- Scale attention scores using √d_k to maintain stable gradients during backpropagation.

## Anti-Patterns
- Avoid computing attention for the entire sequence without applying a causal mask. This allows future tokens to attend to past tokens, breaking the flow of information processing.
- Do not use attention mechanisms in models where causality is irrelevant (e.g., image classification tasks).
- Overfitting by not using dropout or other regularization techniques can reduce model generalization.

## Code Examples
```
class ScaledDotProductAttention(nn.Module):
    def __init__(self, dim: int, dropout: float = 0.1):
        super().__init__()
        self.dim = dim
        self.dropout = nn.Dropout(dropout)
        
        # Compute d_k (k is the dimension of keys) from input size
        self.register_buffer('d_k', torch.tensor(self.dim // 3))
        
    def forward(self, x: Tensor) -> Tensor:
        # Get shape information
        batch_size, seq_len, embed_dim = x.size()
        assert embed_dim == self.dim, "Sequence dimension must match embedding dimension"
        
        # Project input sequence to query, key, and value spaces at the attention layer level
        q, k, v = self.query(x), self.key(x), self.value(x)
        
        # Compute scaled dot product attention scores
        attn_scores = torch.bmm(q.unsqueeze(1),
                               k.unsqueeze(2).transpose(1, 2))
        attn_scores = attn_scores / math.sqrt(self.dim)
        
        # Apply causal mask to scores before softmax
        if seq_len > self.dim:
            # Create lower triangular mask with ones (with the first diagonal element set to zero)
            dim5 = torch.tril(torch.ones(seq_len, seq_len), diagonal=-1).to(attn_scores.device)
            dim5 = dim5.view(1, 1, seq_len, seq_len)
            
            # Apply the causal mask
            attn_mask = (dim5 > 0).float()
            attn_scores = attn_scores.masked_fill(attn_mask == 0, float('-inf'))
        
        # Normalize scores with softmax
        attn_weights = F.softmax(attn_scores, dim=-1)
        
        # Apply dropout to the attention weights
        attn_weights = self.dropout(attn_weights)
        
        # Context vectors are computed as the weighted sum of values
        context_vecs = torch.bmm(attn_weights, v)
        
        return context_vecs.squeeze(2)  # Remove singleton dimension from output
    
    def query(self, x: Tensor) -> List[Tensor]:
        """Computes query, key, and value vectors for a given input tensor."""
        return [self.query(x), self.key(x), self.value(x)]
```

## Reference Tables
| Parameter | Value | Description |
|---|---|---|
| **dim** | 384 | Dimension of the embedding space used in attention mechanisms. |
| **head count** | 8 | Number of attention heads in multi-head attention models. |
| **embedding dimension per head** | 48 | Dimension of each key/value/query vector within a head. |
| **dropout rate** | 0.1 | Probability of dropping neurons during training to prevent overfitting. |

## Key Takeaways
1. Attention mechanisms enable models to dynamically focus on relevant parts of input data.
2. Scaled dot product attention provides numerical stability and improved performance compared to raw dot products.
3. Multi-head attention allows modeling diverse contextual relationships while maintaining computational efficiency.
4. Causal masks prevent future tokens from influencing the model's output at each position, crucial for sequence modeling tasks.
5. Dropout is essential for regularization in attention layers to prevent overfitting.

## Connects To
- Chapter 2: Input and Output Processing (Discussed foundational concepts of tokenization, embeddings, and normalization).
- Chapter 4: Coding transformer components (Builds upon the mechanisms introduced here for more complex models).

This chapter provides a comprehensive understanding of how attention mechanisms work and how to implement them efficiently in PyTorch. The concepts learned here form the basis for developing more advanced models discussed in later chapters.