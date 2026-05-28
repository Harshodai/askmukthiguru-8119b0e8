# Chapter 31: 1. Installation of Necessary Libraries: The initial

## Core Idea
This chapter introduces the essential libraries required for implementing text summarization, knowledge graph creation, and output parsing using LangChain.

## Frameworks Introduced
- **Named Entity Recognition (NER)**: Identifies entities in text, crucial for organizing information.
  - When to use: For extracting specific entities like people, places, or organizations from text.
  - How: Utilizes pre-trained models to identify named entities and structures them into a knowledge graph.

- **Relation Extraction (RE)**: Extracts relationships between identified entities.
  - When to use: For understanding connections between entities in text.
  - How: Uses prompts to guide language models to identify and format relationships as triples.

- **Output Parsers**: Structures the output from language models using Pydantic models.
  - When to use: For formatting structured data into a specific schema.
  - How: Validates and formats outputs to ensure consistency and relevance.

## Key Concepts
- **Few-Shot Learning**: A technique where LLMs are trained on a few examples to generate accurate outputs for new tasks.
- **Output Validation**: Ensures structured and consistent output from language models using Pydantic schemas.
- **Knowledge Graphs**: Represents information as nodes (entities) and edges (relationships), visualized using tools like NetworkX and Pyvis.

## Mental Models
- Use NLP techniques like Named Entity Recognition and Relation Extraction when working with unstructured text to organize and understand information effectively.

## Anti-patterns
- Over-reliance on examples without validation can lead to inconsistent or irrelevant outputs.
- Improper input formatting can disrupt the functionality of prompting systems.

## Code Examples
```python
# Example code for knowledge graph visualization using NetworkX and Pyvis

from langchain.prompts import PromptTemplate  
from langchain.llms import OpenAI 
from langchain.chains import LLMChain  
from networkx import Graph as nxGraph  
import pyvis.network as pyvisNetwork  

# Create a prompt template for knowledge triple extraction  
DEFAULT_KNOWLEDGE_TRIPLE_EXTRACTION_PROMPT = ( 
    "You are a networked intelligence helping a human track knowledge triples"  
    " about all relevant people, things, concepts, etc. and integrating"  
    " them with your knowledge stored within your weights"  
    " as well as that stored in a knowledge graph."  
    " Extract all of the knowledge triples from the text."  
    " A knowledge triple is a clause that contains a subject, a predicate,"  
    " and an object. The subject is the entity being described,"  
    " the predicate is the property of the subject that is being"  
    " described, and the object is the value of the property. \n\n" 
    f"Output: (N{subject}, is the capital of, France) {KG_TRIPLE_DELIMITER }(N{subject}, is in, Paris)}\n" 
    "(Paris, is the capital of, France)"  
)

KNOWLEDGE_TRIPLE_EXTRACTION_PROMPT = PromptTemplate(  
    input_variables =["text"], 
    template =_DEFAULT_KNOWLEDGE_TRIPLE_EXTRACTION_TEMPLATE,  
)  

# Instantiate the OpenAI model  
llm = OpenAI(model_name ="gpt-3.5-turbo" , temperature =0.9)  

# Create an LLMChain using the knowledge triple extraction prompt  
chain = LLMChain(llm =llm, prompt =KNOWLEDGE_TRIPLE_EXTRACTION_PROMPT)  

# Run the chain with the specified text  
text = """The city of Paris is the capital and most populous city of
France. The Eiffel Tower is a famous landmark in Paris."""  
triples = chain.run(text)  

print(triples)
(Paris, is the capital of, France)<|>(Paris, is the most populous
city of, France)<|>(Eiffel Tower, is a, landmark)<|>(Eiffel Tower,
is in, Paris)
```

## Reference Tables

### Parameter Table: LangChain Libraries
| Library          | Function                          | Required Parameters |
|------------------|-----------------------------------|---------------------|
| langchain-chains  | LLMChain                           | llm, prompt          |
| tiktoken         | Tokenizer                          | model_name, temperature |
| openai           | OpenAIModel                       | model_name, API_key   |

### Parameter Table: Output Parsers
| Library     | Pydantic Model | Required Fields      | Validation Criteria  |
|------------|----------------|----------------------|---------------------|
| Pydantic    | ArticleSummary | title, summary       | At least three points |

## Key Takeaways
1. Install necessary Python packages for text processing and AI integration.
2. Leverage NLP techniques like Named Entity Recognition and Relation Extraction for structured information extraction.
3. Use output parsers to validate and format language model responses into a specific schema.
4. Create knowledge graphs from textual data using NetworkX and Pyvis for enhanced data visualization.

## Connects To
- Chapter 1: Text Processing Fundamentals
- Chapter 2: Text Generation Techniques