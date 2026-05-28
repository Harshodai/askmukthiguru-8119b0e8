# Chapter 19: Retrieval Systems in Information Technology

## Core Idea  
This chapter explores advanced retrieval systems designed to enhance information access beyond traditional keyword searches by leveraging dense retrieval and reranking techniques.

## Frameworks Introduced  
- **BM25 Okapi**: A leading lexical search algorithm that ranks documents based on their relevance to a query.  
  - When to use: Ideal for scenarios requiring precise and efficient text matching.  
  - How: Tokenizes input text, removes punctuation, filters out stop words, and scores documents using term frequency and inverse document frequency.

## Key Concepts  
- **Tokenization**: The process of breaking text into meaningful tokens for indexing and searching.  
- **Dense Retrieval**: A method that represents documents in a dense vector space rather than a sparse bag-of-words model.  
- **Reranking**: A technique to refine search results by re-ranking them based on additional criteria or models.

## Mental Models  
Use BM25 Okapi when you need fast and accurate keyword-based searches, especially for technical or scientific documents. Think of dense retrieval as an advanced version of BM25 that provides more context-rich results.

## Anti-patterns  
- **Over-reliance on Keyword Search**: This approach fails to capture nuanced query intent and often misses relevant results.

## Code Examples  
```python
def bm25_tokenizer(text):
    tokenized_doc = []
    for token in text.lower().split():
        token = token.strip(string.punctuation)
        if len(token) > 0 and token not in _stop_words.ENGLISH_STOP_WORDS:
            tokenized_doc.append(token)
    return tokenized_doc

tokenized_corpus = []
for passage in tqdm(texts):
    tokenized_corpus.append(bm25_tokenizer(passage))

bm25 = BM25Okapi(tokenized_corpus)

def keyword_search(query, top_k=3, num_candidates=15):
    print("Input question:", query)
    
    bm25_scores = bm25.get_scores(bm25_tokenizer(query))
    top_n = np.argpartition(bm25_scores, -num_candidates)[-num_candidates:]
    
    bm25_hits = [{'corpus_id': idx, 'score': bm25_scores[idx]} for idx in top_n]
    bm25_hits = sorted(bm25_hits, key=lambda x: x['score'], reverse=True)
    
    print(f"Top-3 lexical search (BM25) hits")
    for hit in bm25_hits[:top_k]:
        print(f"{hit['score']:.3f}\t{texts[hit['corpus_id']].replace('\n', ' ')}")
```

## Reference Tables  
| Parameter | Value/Definition |
| --- | --- |
| **BM25 Okapi** | Uses term frequency (TF) and inverse document frequency (IDF) to score documents. |

## Key Takeaways  
1. Use BM25 Okapi for fast and precise keyword-based searches in technical documents.  
2. Dense retrieval provides more context-rich results by considering word embeddings or other dense representations.  
3. Reranking can refine search results by applying additional criteria beyond keyword matching.

## Connects To  
- Relates to reranking techniques and chunking methods discussed in subsequent chapters.