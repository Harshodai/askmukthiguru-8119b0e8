# Technical Patterns

Here is a structured presentation of the technical techniques from the provided chapter titles:

---

### **1. Quick-Reference Tables**
**Pattern Name:** Quick-Reference Tables  
**When to Use:** When you need a fast lookup for information during processing.  
**How:** Refer to predefined tables or charts for quick access to data or parameters.  
**Trade-offs:** May not provide detailed explanations but offer speed and simplicity.

---

### **2. Load Document and Extract Raw Text**
**Pattern Name:** Text Extraction from Documents  
**When to Use:** When you need to process raw text from documents.  
**How:** Parse the document into its constituent text segments.  
**Trade-offs:** May lose contextual or formatted information.

---

### **3. RAG for Structured Data**
**Pattern Name:** Retrieval-Augmented Generation for Structured Data  
**When to Use:** When dealing with structured data like databases or tables.  
**How:** Apply RAG techniques tailored to structured formats, ensuring accurate data retrieval and generation.  
**Trade-offs:** May require additional processing to maintain data structure integrity.

---

### **4. Load CSV File and Parse into Rows**
**Pattern Name:** Data Parsing from CSV Files  
**When to Use:** When working with comma-separated values (CSV) files.  
**How:** Convert the file into a tabular format for easier manipulation and analysis.  
**Trade-offs:** Assumes well-formatted data without missing fields.

---

### **5. Reliable RAG: Building Trust Through**
**Pattern Name:** Enhancing RAG's Reliability  
**When to Use:** When trust in the system is critical, such as in sensitive applications.  
**How:** Implement methods to ensure accurate and consistent retrieval and generation.  
**Trade-offs:** May require additional computational resources for reliability checks.

---

### **6. Proposition Chunking: Breaking**
**Pattern Name:** Text Chunking into Propositions  
**When to Use:** When you need to segment text into meaningful propositions or clauses.  
**How:** Identify key components of a text and group them into logical chunks.  
**Trade-offs:** May lose some contextual nuances depending on chunk size.

---

### **7. Split Document into Initial Text Chunks**
**Pattern Name:** Initial Text Chunking  
**When to Use:** When you need to divide a document into manageable parts for processing.  
**How:** Divide the text into smaller, readable chunks based on readability or context boundaries.  
**Trade-offs:** May require careful selection of chunk sizes to avoid losing meaning.

---

### **8. Query Transformations: Reshaping the Question**
**Pattern Name:** Query Transformation Strategies  
**When to Use:** When user queries are ambiguous or need rephrasing for better understanding.  
**How:** Modify the query using rewriting, step-wise, or expanding strategies.  
**Trade-offs:** May require additional processing time and natural language understanding.

---

### **9. LLM Generates a More Specific, Detailed Version**
**Pattern Name:** Language Model Augmentation  
**When to Use:** When you need more detailed responses from a large language model (LLM).  
**How:** Use the LLM to generate a refined version of the initial response.  
**Trade-offs:** May require additional computational resources and time.

---

### **10. Run Vector Search Independently for Each Sub-Query**
**Pattern Name:** Parallel Vector Search  
**When to Use:** When performing multiple vector searches simultaneously.  
**How:** Execute each sub-query independently using vector search techniques.  
**Trade-offs:** May reduce efficiency if not properly optimized.

---

### **11. Receive the Generated Answer and the Source Documents**
**Pattern Name:** Answer Retrieval with Source Documents  
**When to Use:** When you need both a generated answer and its supporting evidence.  
**How:** Retrieve the answer along with the source documents that provided the information.  
**Trade-offs:** May require additional storage for source documents.

---

### **12. Proposition Chunking: Breaking**
**Pattern Name:** Text Chunking into Propositions (Revised)  
**When to Use:** When you need to segment text into meaningful propositions or clauses.  
**How:** Identify key components of a text and group them into logical chunks.  
**Trade-offs:** May lose some contextual nuances depending on chunk size.

---

### **13. Contextual Chunk Headers: Giving**
**Pattern Name:** Adding Context to Chunks  
**When to Use:** When you need context-specific information about each chunk.  
**How:** Prepend metadata, such as document titles or summaries, to each chunk.  
**Trade-offs:** May require additional storage for metadata.

---

### **14. Context Enrichment Window**
**Pattern Name:** Enhancing Context Around Chunks  
**When to Use:** When you need improved context around text chunks.  
**How:** Apply a window-based approach to enhance contextual information.  
**Trade-offs:** May require additional processing time and resources.

---

### **15. Semantic Chunking: Splitting Text**
**Pattern Name:** Semantic Text Chunking  
**When to Use:** When you need to split text into semantically meaningful chunks.  
**How:** Group text based on meaning rather than arbitrary boundaries.  
**Trade-offs:** May require advanced NLP techniques for accurate chunking.

---

### **16. Split Document into Individual Sentences**
**Pattern Name:** Sentence-Level Text Chunking  
**When to Use:** When you need to divide a document into individual sentences.  
**How:** Parse the text into separate sentences based on punctuation and context boundaries.  
**Trade-offs:** May lose some contextual nuances depending on sentence length.

---

### **17. Contextual Compression: Extracting Key Information**
**Pattern Name:** Contextual Compression  
**When to Use:** When you need to extract key information from a document.  
**How:** Compress the context while retaining important details.  
**Trade-offs:** May require careful selection of which information to retain.

---

### **18. Fusion Retrieval: Combining Keyword and Vector Search**
**Pattern Name:** Fusion Retrieval  
**When to Use:** When you need to combine keyword search with vector search for better results.  
**How:** Integrate both methods to retrieve more relevant documents.  
**Trade-offs:** May require additional processing time and resources.

---

### **19. Three Query Transformation Strategies**
**Pattern Name:** Query Transformation Techniques (Rewriting, Step-Wise, Expanding)  
**When to Use:** When user queries are ambiguous or need rephrasing for better understanding.  
**How:** Modify the query using rewriting, step-wise, or expanding strategies.  
**Trade-offs:** May require additional processing time and natural language understanding.

---

### **20. Hierarchical Indices**
**Pattern Name:** Efficient Retrieval with Hierarchical Indices  
**When to Use:** When you need efficient retrieval of information from a large dataset.  
**How:** Organize data using hierarchical indices for faster search.  
**Trade-offs:** May require additional storage and indexing complexity.

---

### **21. Reranking Candidate Chunks**
**Pattern Name:** Improving Retrieval Accuracy  
**When to Use:** When you need to select the most relevant chunks from a large set of candidates.  
**How:** Rank candidate chunks based on relevance metrics.  
**Trade-offs:** May require additional computational resources and time.

---

### **22. Multi-Modal RAG with Captioning**
**Pattern Name:** Retrieval-Augmented Generation with Multi-Modal Data  
**When to Use:** When dealing with data that includes both text and images.  
**How:** Integrate visual data into the RAG system for enhanced context.  
**Trade-offs:** May require additional resources for handling multi-modal data.

---

### **23. Storing Position Metadata During Chunking**
**Pattern Name:** Metadata Storage for Chunks  
**When to Use:** When you need metadata about each chunk's position in the original document.  
**How:** Keep track of where each chunk was extracted from the original text.  
**Trade-offs:** May require additional storage for metadata.

---

### **24. Contextual Compression: Extracting Key Information (Revised)**
**Pattern Name:** Contextual Compression  
**When to Use:** When you need to extract key information from a document.  
**How:** Compress the context while retaining important details.  
**Trade-offs:** May require careful selection of which information to retain.

---

### **25. Dartboard Retrieval**
**Pattern Name:** Dartboard Retrieval  
**When to Use:** When you need a specific method for retrieval, possibly involving scoring or ranking.  
**How:** Use a dartboard-like algorithm for retrieval.  
**Trade-offs:** May require additional resources and complexity.

---

### **26. Computing Distance from Query to Each Candidate**
**Pattern Name:** Retrieval with Distance Calculation  
**When to Use:** When you need to measure the similarity between a query and candidate chunks.  
**How:** Calculate distance metrics (e.g., cosine similarity) for each chunk.  
**Trade-offs:** May require additional computational resources.

---

### **27. Multi-Modal RAG with Captioning**
**Pattern Name:** Retrieval-Augmented Generation with Multi-Modal Data  
**When to Use:** When dealing with data that includes both text and images.  
**How:** Integrate visual data into the RAG system for enhanced context.  
**Trade-offs:** May require additional resources for handling multi-modal data.

---

### **28. Fusion Retrieval: Combining Keyword and Vector Search**
**Pattern Name:** Fusion Retrieval  
**When to Use:** When you need to combine keyword search with vector search for better results.  
**How:** Integrate both methods to retrieve more relevant documents.  
**Trade-offs:** May require additional processing time and resources.

---

### **29. Receiving the Generated Answer and the Retrieved Context**
**Pattern Name:** Integrating Generated Answers with Context  
**When to Use:** When you need both a generated answer and its supporting context.  
**How:** Retrieve the answer along with the source documents that provided the information.  
**Trade-offs:** May require additional storage for source documents.

---

This structured presentation provides an organized overview of the techniques covered in each chapter, highlighting their applications, methods, and potential trade-offs.