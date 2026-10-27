# Chapter 40: Trying out LangChain

## Core Idea
This chapter teaches how to leverage LangChain's capabilities for creating structured text summarizations by crafting effective prompts and composing tasks into chains.

## Frameworks Introduced
- **Prompt Engineering**: A methodical approach to designing prompts that yield optimal responses.  
  - When to use: Whenever you need a reliable way to generate consistent and high-quality outputs from an AI model.
  - How: Craft prompts with clear instructions, including placeholders for parameters like number of words or tone.

## Key Concepts
- **Prompt Template**: A structured format used to generate specific types of responses by filling in input parameters.  
- **LCEL (LangChain Expression Language)**: A declarative syntax for defining chains of tasks using LangChain components.
- **Chain Composition**: Building a sequence of interconnected tasks to achieve a desired outcome.

## Mental Models
- Use compose when you have sequential tasks that need to be executed in order, ensuring each step feeds into the next.  
  - Example: Compose a chain where web scraping is followed by summarization and emailing to automate data processing workflows.

## Anti-patterns
- **Monolithic Code**: Avoid writing large blocks of code without breaking them into reusable components.
  - Why it fails: Makes debugging, maintenance, and collaboration difficult.

## Code Examples

### Example 1: Prompt Engineering with `llm.invoke()`
```python
from langchain_core.prompts import PromptTemplate

segovia_aqueduct_text = """The Aqueduct of Segovia (Spanish: Acueducto de Segovia) is a Roman aqueduct in Segovia, Spain. It was built around the first century AD to channel water from springs in the mountains 17 kilometres (11 mi) away to the city's fountains, public baths and private houses, and was in use until 1973. Its elevated section, with its complete arcade of 167 arches, is one of the best-preserved Roman aqueduct bridges and the foremost symbol of Segovia, as evidenced by its presence on the city's coat of arms. The Old Town of Listing A.1 Creating a prompt from a PromptTemplate
Segovia and the aqueduct, were declared a UNESCO World Heritage Site in 1985. As the aqueduct lacks a legible inscription (one was apparently located in the structure's attic, or top portion[citation needed]), the date of construction cannot be definitively determined. The general date of the Aqueduct's construction was long a mystery, although it was thought to have been during the 1st century AD, during the reigns of the Emperors Domitian, Nerva, and Trajan. At the end of the 20th century, Géza Alföldy deciphered the text on the dedication plaque by studying the anchors that held the now missing bronze letters in place. He determined that Emperor Domitian (AD 81–96) ordered its construction[1] and the year 98 AD was proposed as the most likely date of completion.[2] However, in 2016 archeological evidence was published which points to a slightly later date, after 112 AD, during the government of Trajan or in the beginning of the government of emperor Hadrian, from 117 AD."""
prompt_template = PromptTemplate.from_template("""You are an experienced copywriter. Write a {num_words} words summary of the following text, using a {tone} tone: {text}""")
prompt_input = prompt_template.format(text=segovia_aqueduct_text, num_words=20, tone="knowledgeable and engaging")
response = llm.invoke(prompt_input)
print(response.content)

```
This code demonstrates how to use LangChain's `PromptTemplate` class to generate a concise summary of the Aqueduct of Segovia text.

### Example 2: LCEL for Chain Composition
```python
from langchain chains import web_scraping, summarization, emailing

chain = web_scraping | summarization | emailing
```
This code shows how to define a chain using LCEL syntax to automate the process of scraping news, summarizing it, and emailing the summary.

## Reference Tables
| Framework       | Purpose                                      |
|-----------------|------------------------------------------------|
| Prompt Engineering | Crafting effective prompts for AI models    |
| LCEL            | Syntax for defining LangChain chains        |

## Key Takeaways
1. Use prompt engineering to create clear and effective prompts for consistent outputs.
2. Compose tasks into chains using LCEL or other methods to automate workflows.
3. Understand the principles of chain composition to build scalable solutions.

## Connects To
- Relates to chapter 2 on prompt templates and chapter 5 on LCEL for chain composition.