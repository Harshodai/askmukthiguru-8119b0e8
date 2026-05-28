# Chapter 30: Error Fixing with Output Parsers

## Core Idea
This chapter introduces error-fixing techniques using PydanticOutputParser and RetryOutputParser to enhance model outputs by correcting validation errors.

## Frameworks Introduced
- **PydanticOutputParser**: Validates and fixes output based on Pydantic schemas.
  - When to use: When model outputs need validation against structured data.
  - How: Automatically corrects field name mismatches or missing keys.
  
- **RetryOutputParser**: Iteratively refines incorrect outputs by prompting for context.
  - When to use: When outputs require additional information to resolve issues.
  - How: Asks the model for clarification in prompt-based setups.

## Key Concepts
- **PydanticOutputParser**: Validates and corrects output using Pydantic models.
- **RetryOutputParser**: Iteratively refines outputs by prompting for context or details.

## Mental Models
Use PydanticOutputParser when you need immediate fixes based on schema validation. Think of it as automatically adjusting outputs to match the model's expectations.

## Anti-patterns
Avoid not using these parsers, which can lead to more errors than manual corrections.

## Code Examples
```python
from langchain.output_parsers import PydanticOutputParser, RetryOutputParser
from pydantic import BaseModel

# Example for PydanticOutputParser
class Suggestions(BaseModel):
    words: List[str] = Field(description="list of substitute words based on context")
    reasons: List[str] = Field(description="the reasoning of why this word fits the context")

parser = PydanticOutputParser(pydantic_object=Suggestions)
missformatted_output = '{"words": ["conduct", "manner"], "reasons": [...]}'
parser.parse(missformatted_output)

# Example for RetryOutputParser
from langchain.prompts import PromptTemplate

template = """Offer a list of suggestions to substitute the specified target_word based on the presented context and the reasoning for each word."""
prompt = PromptTemplate(template=template, input_variables=["target_word", "context"])

model_input = prompt.format_prompt(target_word="behaviour", context="The behaviour of the students in the classroom was disruptive.")

retry_parser = RetryOutputParser.from_llm(parser=parser, llm=model)
retry_parser.parse_with_prompt(missformatted_output, model_input)
```

## Reference Tables
| Framework        | Purpose                                      |
|------------------|------------------------------------------------|
| PydanticOutputParser | Fixes output validation errors using Pydantic schemas. |
| RetryOutputParser  | Iteratively refines incorrect outputs with context. |

## Key Takeaways
1. Use PydanticOutputParser when you need immediate fixes based on schema validation.
2. Think of it as automatically adjusting outputs to match the model's expectations.
3. Avoid not using these parsers, which can lead to more errors than manual corrections.

This chapter emphasizes leveraging these tools for structured output correction and highlights their benefits over manual error fixing approaches.