# Chapter 12: Text Classification Using Pretrained Models and Generative Approaches  

## Core Idea  
Text classification can be efficiently achieved using pretrained language models, whether through fine-tuning task-specific models like RoBERTa or leveraging embeddings for zero-shot classification with generative models like Flan-T5.  

## Frameworks Introduced  
1. **Pretrained Task-Specific Models (e.g., RoBERTa)**: Fine-tune on domain-specific tasks using labeled data.  
   - When to use: When you have labeled training data and want high performance on specific tasks.  
   - How: Load the model, fine-tune it on your dataset, then use it for inference.

2. **Embedding-Based Models (e.g., sentence-transformers)**: Use embeddings for classification without fine-tuning a large model.  
   - When to use: When you have limited or no labeled data and want to leverage precomputed embeddings.  
   - How: Generate dense vector representations of text and train a classifier on these embeddings.

3. **Generative Models (e.g., Flan-T5, GPT-3.5-turbo-0125)**: Use for text-to-text tasks without requiring domain-specific training data during inference.  
   - When to use: When you need to generate human-like text outputs and have access to external APIs or cloud services.  
   - How: Define a prompt instructing the model to perform the desired task, then generate text based on input documents.

## Key Concepts  
- **Pretrained Models**: Models like RoBERTa are trained on large datasets (e.g., 500M tokens) and can be fine-tuned for specific tasks.  
- **Embedding Models**: Techniques like sentence-transformers convert text into dense vectors that can be used as features for classification.  
- **Generative Models**: Models like Flan-T5 and GPT-3.5 are trained on diverse datasets and can generate human-like text without requiring domain-specific training data during inference.

## Mental Models  
Use RoBERTa when you have labeled training data and need high accuracy on specific tasks. Think of embeddings as a way to leverage precomputed vector representations for classification without fine-tuning large models. Use generative models like Flan-T5 when you need to generate human-like text outputs from input documents.

## Anti-Patterns  
- **Overfitting**: Avoid using overly complex models (e.g., GPT-3.5) for simple tasks that could be handled by smaller models like Flan-T5.  
- **Ignoring Pretrained Models**: Do not discard pretrained models; they often contain valuable domain knowledge that can be repurposed with minimal adjustments.

## Code Examples  
### RoBERTa-Based Pipeline  
```python
from transformers import pipeline
# Load and run the model for classification
pipe = pipeline("text-classification", model="roberta-base-sentiment-latest ")
y_pred = []
for output in tqdm(pipe(KeyDataset (data["test"], "text")), total=len(data["test"])):
    negative_score , positive_score = output[0]["score"]
    prediction = np.argmax([negative_score, positive_score ])
    y_pred.append( int(prediction) )
```
This demonstrates how to use a pretrained RoBERTa model for supervised text classification.

### Embedding-Based Approach  
```python
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.linear_model import LogisticRegression

# Create embeddings
train_embeddings = model.encode(data["train"]["text"], show_progress_bar=True)
test_embeddings  = model.encode(data["test"]["text"], show_progress_bar=True)

# Train a classifier
clf = LogisticRegression (random_state=42)
clf.fit(train_embeddings, data["train"]["label"])
y_pred = [ int(clf.predict(test_embeddings )) ]
```
This shows how to use embeddings for zero-shot classification.

### Flan-T5 Model  
```python
from openai import OpenAI

client = openai.OpenAI(api_key="YOUR_KEY_HERE")
def chatgpt_generation(prompt, document):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt.replace("[DOCUMENT] ", document )}
    ]
    completion = client.chat.completions.create(
      messages=messages,
      model="flan-t5-small/base/lar ge/xl/xxl",
      temperature=0
    )
    return completion.choices[0].message.content

# Generate predictions
y_pred = [ int( chatgpt_generation ( "Predict whether the following document is a positive or negative movie review: ", doc )) for doc in data["test"]["text"] ]
```
This example illustrates using Flan-T5 for text classification without labeled training data.

## Reference Tables  
| Model Architecture | Pre-training Task | Use Case Example |
|--------------------|-------------------|------------------|
| Encoder-Only (e.g., RoBERTa) | General NLP tasks | Sentiment analysis, document classification |
| Decoder-Only (e.g., GPT-3.5-turbo-0125) | Text generation | Text summarization, text-to-text translation |
| Hybrid Models (e.g., Flan-T5) | Pre-training on diverse texts | Text classification without labeled data |

## Key Takeaways  
1. Use pretrained models like RoBERTa for supervised tasks when you have labeled training data.  
2. Leverage embeddings for zero-shot classification when labeled data is scarce.  
3. Utilize generative models like Flan-T5 for text generation tasks where domain-specific training data is unavailable.

## Connects To  
- Chapter 10: Fine-tuning and Pretrained Models  
- Chapter 11: Text Generation with Sequence-to-Sequence Models