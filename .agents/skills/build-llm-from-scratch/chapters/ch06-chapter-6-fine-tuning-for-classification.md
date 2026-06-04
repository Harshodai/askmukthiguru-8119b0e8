# Chapter 6: Fine-tuning for classification

## Core Idea
This chapter teaches how to fine-tune large language models (LLMs) for classification tasks, such as spam detection, by leveraging pre-trained models and adapting them to specific prediction goals.

## Frameworks Introduced
- **GPT Architecture**: A 3.5B-parameter model based on transformer-based attention mechanisms, used for text generation and classification.
  - When to use: Pre-trained for NLP tasks requiring contextual understanding.
- **Instruction-Fine-tuning Framework**: Adapting pre-trained LLMs to follow specific instructions or perform designated tasks.
  - When to use: For creating specialized chatbots or personal assistants.

## Key Concepts
- **Classification Task**: Assigning text to predefined categories (e.g., spam vs. non-spam).
- **Preprocessing Pipeline**: Converting raw text into token IDs, handling missing values, and normalizing sequences.
- **Cross-Entropy Loss**: Used for training classification models by measuring prediction accuracy.

## Mental Models
- Use GPT architecture when you need a model capable of understanding context and generating coherent text.
- Think of instruction-fine-tuning as adapting an LLM to follow specific instructions or perform designated tasks.

## Anti-patterns
- **Overfitting Without Validation**: When the model memorizes training data instead of generalizing, indicated by high accuracy on training but low on validation.
- **Ignoring Preprocessing Steps**: Failing to normalize text can lead to biased or inconsistent results.

## Code Examples
```python
def classify_review(
    text, model, tokenizer, device, max_length=None,
    pad_token_id=50256):
    model.eval()
    input_ids = tokenizer.encode(text)         
    supported_context_length = model.pos_emb.weight.shape[1]
    input_ids = input_ids[:min(  
        max_length, supported_context_length
    )]
    input_ids += [pad_token_id] * (max_length - len(input_ids))   
    
    input_ids_tensor = torch.tensor(
        input_ids, device=device
    ).unsqueeze(0)             
    
    with torch.no_grad():                               
    logits = model(input_ids_tensor)[:, -1, :]    
    predicted_label = torch.argmax(logits, dim=-1).item()
    return "spam" if predicted_label == 1 else "not spam"
```
This demonstrates how to classify text using a pre-trained LLM by adapting its output layer for binary classification.

## Reference Tables
| Framework                | Key Application                          |
|-------------------------|----------------------------------------|
| GPT Architecture         | Text generation, summarization       |
| Instruction-Fine-tuning  | Following specific instructions          |

## Key Takeaways
1. Implement a preprocessing pipeline to convert text into token IDs.
2. Fine-tune the model using appropriate hyperparameters and validation strategies.
3. Monitor classification metrics like accuracy and loss during training.

## Connects To
- Chapter 5: Pretraining for generation tasks
- Chapter 7: Instruction fine-tuning framework