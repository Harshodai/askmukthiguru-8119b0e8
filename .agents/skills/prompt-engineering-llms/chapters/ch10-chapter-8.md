```markdown
# Chapter 10: CHAPTER 8

## Core Idea
Enabling conversational agents with external tools expands their functionality beyond chat models by allowing them to access real-world data, perform non-language tasks, and interact with the environment.

## Frameworks Introduced
- **Tool Usage**: 
  - When to use: When tasks require accessing external information or performing real-world actions.
  - How: Integrate JSON schemas for tool definitions and map functions to available APIs within the model.

## Key Concepts
- **Tool-Usage**: Integration of predefined tools into language models to enable external interactions.
- **API Calls**: Communication with external systems via well-defined interfaces.
- **Contextual Awareness**: Accessing and incorporating real-world information beyond training data.

## Mental Models
- Use API calls when you need the model to interact with external systems or retrieve specific information.
- Think of JSON schemas as structured blueprints for tool functionality.

## Anti-patterns
- **Relying solely on internal knowledge**: Without tools, models are limited to what they were trained on and cannot access up-to-date information.

## Code Examples
```python
def process_messages(client, messages):
    # Step 1: send the messages to the model along with the tool definitions
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
    )
    response_message = response.choices[0].message
    # Step 2: append the model's response to the conversation
    messages.append(response_message)
    # Step 3: check if the model wanted to use a tool
    if response_message.tool_calls:
        # Step 4: extract tool invocation and make evaluation
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(
                **function_args
            )
            # Step 5: extend conversation with function response
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )
```
- This demonstrates how a model can process user requests, invoke predefined tools, and incorporate external responses into its output.

## Reference Tables
<No reference tables are present in this chapter.>

## Key Takeaways
1. Use API calls when you need the model to interact with external systems or retrieve specific information.
2. Leverage JSON schemas for tool definitions to structure interactions with external APIs.
3. Ensure contextual awareness by incorporating real-world data and actions into conversational agents.

## Connects To
- Relates to previous discussions on LLM limitations (Chapter 3) and future topics like advanced tooling (Chapter 9).
```