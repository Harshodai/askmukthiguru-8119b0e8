# Chapter 15: 1. Tasks: SuperGLUE has eight diverse language

## Core Idea  
This chapter introduces three benchmarks—SuperGLUE, BIG-Bench, and HELM—that provide structured frameworks for evaluating large language models across a wide range of tasks, helping researchers compare model performance systematically.

## Frameworks Introduced  
- **SuperGLUE**: A benchmark with eight diverse tasks (boolean question answering, textual entailment, coreference resolution, reading comprehension, and word-sense disambiguation) designed to challenge NLP models beyond GLUE's limitations.  
  - When to use: For evaluating models on fundamental language understanding tasks.  
  - How: By running models through predefined tasks with standardized outputs for comparison.

- **BIG-Bench**: A comprehensive benchmark comprising over 204 language tasks across multiple domains, including code writing, common-sense reasoning, and game playing, evaluated using JSON-based comparisons or programmatic Python assessments.  
  - When to use: For testing advanced models on complex, varied tasks requiring structured outputs or conditional probability assessments.  
  - How: By evaluating model outputs against target pairs (JSON) or generating text with Python scripts for evaluation.

- **HELM**: A holistic benchmark focusing on broad coverage and recognition of incompleteness in language understanding, designed to address gaps in current benchmarks by incorporating diverse scenarios and user-centric applications.  
  - When to use: For comprehensive evaluations that require testing models across multiple domains and scenarios.  
  - How: By structuring assessments around three main components: broad coverage, recognition of incompleteness, and alignment with user needs.

## Key Concepts  
- **JSON tasks**: Tasks evaluated by comparing output and target pairs in JSON format.  
- **Programmatic tasks**: Tasks assessed using Python scripts to evaluate text generation and conditional log probabilities.  
- **Code writing**: A task where models generate code snippets or complete programs, evaluated for accuracy and syntax correctness.  
- **Common-sense reasoning**: Tasks requiring models to infer knowledge implicitly rather than explicitly stated in the input.  

## Mental Models  
Use SuperGLUE when you need a lightweight benchmark for fundamental language understanding tasks. Think of BIG-Bench as a tool for testing advanced capabilities like code generation or game playing. Use HELM to ensure your evaluation framework covers a wide range of scenarios and user needs.

## Anti-patterns  
- **Avoid ignoring model limitations**: Do not solely rely on larger models, as they may fail in specific scenarios due to scaling issues or sparsity.  

## Code Examples  
```python
# Example code for evaluating BIG-Bench tasks using JSON comparison
def evaluate_model(model, task):
    input = "What is the capital of France?"
    output = model.generate("Answer: ")
    target = {"capital": "Paris"}
    
    # Compare output with target using JSON schema validation
    score = validate_json(output, target)
    return score
```

- **What it demonstrates**: Evaluates how well a model generates structured responses that align with predefined targets.

## Reference Tables  
| Benchmark | Tasks                          | Evaluation Method               |
|-----------|----------------------------------|----------------------------------|
| SuperGLUE  | Boolean question answering,       | Output and target pair comparison |
|           | Textual entailment,             | Automated scoring                |
|           | Coreference resolution,         | Accuracy on coreference tasks    |
|           | Reading comprehension (common-sense), | Standardized reading comprehension datasets |
|           | Word-sense disambiguation       | Accuracy on ambiguous words     |

## Key Takeaways  
1. Use SuperGLUE for evaluating fundamental language understanding tasks.  
2. Leverage BIG-Bench to test advanced capabilities like code generation and game playing.  
3. Incorporate HELM's holistic approach to ensure comprehensive evaluation across diverse scenarios.

## Connects To  
- Relates to discussions on model limitations, scaling, and user-centric applications in later chapters.