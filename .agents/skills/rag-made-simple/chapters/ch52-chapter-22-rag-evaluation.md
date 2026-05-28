# Chapter 52: RAG Evaluation

## Core Idea  
RAG evaluation systematically assesses each stage of a Retrieval-Augmented Generation (RAG) pipeline to diagnose failures and improve performance. It evaluates context relevance, faithfulness, and answer relevance independently.

## Frameworks Introduced  
- **Context Precision**: Measures the fraction of retrieved chunks that are relevant to the query.
  - When to use: To evaluate how well the retriever identifies useful documents.
  - How: Calculate precision at K (top-K retrieved documents) by dividing the number of relevant documents by total retrieved.

- **Mean Reciprocal Rank (MRR)**: Scores systems based on the position of their first correct answer.
  - When to use: For queries with a single best answer.
  - How: Average reciprocal ranks, where rank=1 is highest.

- **Mean Average Precision (MAP)**: Extends MRR for queries with multiple relevant answers.
  - When to use: For queries with multiple correct answers.
  - How: Compute precision at every rank where a relevant document appears and average across all query results.

- **Normalized Discounted Cumulative Gain (NDCG)**: Evaluates ranking quality on a spectrum of relevance.
  - When to use: For graded relevance scenarios.
  - How: Assign scores based on document relevance and position, then normalize against the ideal ranking.

## Key Concepts  
- **Context Precision**: Fraction of retrieved documents that are actually relevant.  
- **MRR**: Average of reciprocal ranks for correct answers.  
- **MAP**: Average precision across all query results with multiple correct answers.  
- **NDCG**: Ranking score based on graded relevance, normalized to a 0-1 scale.

## Mental Models  
Use Context Precision when evaluating retrieval systems. Think of it as measuring how well the retriever identifies useful documents without unnecessary noise.  

Avoid using MAP for queries where all relevant answers must appear at the top, as it may penalize systems that surface correct answers lower in the list.  

Think of NDCG as a way to rank systems based on graded relevance, ensuring higher scores for more accurate and ordered results.

## Anti-patterns  
- **Ignoring intermediate failures**: Focusing only on final outputs hides issues at retrieval or generation stages.
- **Using binary metrics exclusively**: Avoid treating relevance as a yes/no decision; use nuanced metrics like NDCG for better insights.

## Code Examples  
```python
def calculate_precision_at_k(relevant_count, total_retrieved, k):
    if total_retrieved == 0:
        return 0.0
    precision = (relevant_count) / (total_retrieved)
    return precision

def calculate_recall_at_k(relevant_count, retrieved_count, k):
    if retrieved_count == 0:
        return 0.0
    recall = relevant_count / retrieved_count
    return recall
```

**What it demonstrates**: Step-by-step calculation of precision and recall at K for retrieval systems.

## Reference Tables  
| Metric          | Use Case                          | Calculation                     |
|------------------|------------------------------------|-------------------------------|
| Context Precision | Retrieval effectiveness            | (Relevant Documents) / (Retrieved Documents) |
| MRR              | Single best answer per query      | 1 / rank of first correct answer |
| MAP              | Multiple relevant answers         | Average precision at each correct rank position |
| NDCG             | Graded relevance scenarios        | (Sum of graded relevance scores) / Ideal score |

## Key Takeaways  
1. Use Context Precision to evaluate retrieval systems and identify noise in retrieved documents.  
2. Implement MRR for queries with a single best answer to prioritize timely results.  
3. Apply MAP when multiple correct answers exist, rewarding systems that surface all relevant answers early.  
4. Utilize NDCG for scenarios where relevance is graded, ensuring higher scores for accurate and ordered results.

## Connects To  
- Chapter 1: Basic RAG Pipeline (Understanding the stages of retrieval and generation)  
- Chapter 3: Verification Concepts (Ensuring correctness in outputs through systematic evaluation)