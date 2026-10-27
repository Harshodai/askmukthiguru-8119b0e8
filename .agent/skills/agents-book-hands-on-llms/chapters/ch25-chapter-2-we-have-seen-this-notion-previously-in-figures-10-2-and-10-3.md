# Chapter 25: We have seen this notion previously in Figures 10-2 and 10-3.

## Core Idea
This chapter explores the creation and fine-tuning of text embedding models using various tasks, including contrastive learning for paraphrase detection, similarity scoring for document pairs, and denoising auto-encoder for unsupervised learning. The focus is on leveraging pre-trained BER T models and advanced loss functions to improve model performance.

## Frameworks Introduced
### Contrastive Learning with BER T (sentence-transformers)
- **Framework Name**: Contrastive Learning with BER T
  - **When to use**: When working with text data requiring semantic similarity scoring or paraphrase detection.
  - **How**: Utilizes pre-trained BER T models trained on masked language modeling tasks, paired with loss functions like cosine similarity and MNR loss.

## Key Concepts
- **Embedding Model**: A numerical representation of textual data that captures semantic meaning.
- **Cross-Encoder**: Trains a model to score pairs of sentences based on their semantic similarity.
- **Masked Language Modeling (MLM)**: Pre-training task where random tokens in a sentence are replaced with a mask, requiring the model to reconstruct them.
- **Contrastive Learning**: Learning from positive and negative pairs of data points.

## Mental Models
- Use BER T-based models when you need reliable text embeddings for tasks like paraphrase detection or document similarity scoring.
- Think of masked language modeling as a way to pre-train models to understand word relationships.
- Consider using MNR loss to balance hard and easy pairs during training.

## Anti-Patterns
- **Avoid data imbalance**: Ensure your training data has balanced positive and negative examples to prevent biased model outputs.
- **Beware of overfitting on noisy data**: Noisy or irrelevant sentences can degrade model performance if not filtered out.
- **Steer clear of unsupervised learning without labeled data**: Unsupervised techniques like TSDAE require careful implementation and validation.

## Code Examples
```python
from sentence_transformers  import losses, SentenceTransformer
from sentence_transformers .data  import read_dataset

# Define model
embedding_model = SentenceTransformer ('bert-base-uncased ')

# Define loss function (MNR)
train_loss = losses.MultipleNegativesRankingLoss (model=embedding_model, num_labels=100)

# Define training arguments
args = TrainingArguments (
    output_dir ='output',
    num_train_epochs=1,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=32,
    warmup_steps=100,
    fp16=True,
    eval_steps=100,
    logging_steps=100
)

# Train model
trainer = Trainer (
    model=embedding_model ,
    args=args ,
    train_dataset =train_dataset ,
    loss=train_loss ,
    evaluator =evaluator
)
trainer.train()
```

## Reference Tables
| **Loss Function**       | **Description**                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| Cosine Similarity Loss   | Measures similarity between embeddings using cosine similarity.               |
| Multiple Negatives Ranking Loss (MNR) | Encourages model to rank positive pairs higher than negative ones.           |

## Key Takeaways
1. Use BER T-based models for reliable text embedding tasks.
2. Leverage masked language modeling for robust pre-training of BER T models.
3. Evaluate models using appropriate metrics like Spearman’s rho for similarity scoring.
4. Balance between supervised and unsupervised techniques based on available data.

## Connects To
- Relates to Chapter 10's discussion of contrastive learning and semantic tasks.
- Links to Chapter 12's exploration of transfer learning and domain adaptation techniques.