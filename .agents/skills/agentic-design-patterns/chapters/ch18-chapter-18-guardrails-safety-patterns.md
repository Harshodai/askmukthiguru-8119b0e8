# Chapter 18: Guardrails/Safety Patterns

## Core Idea
Guardrails are essential for ensuring AI systems operate safely, ethically, and responsibly by implementing multiple layers of control to prevent harmful or unethical outputs.

## Frameworks Introduced
- **AI Content Policy Enforcer (Gemini/Firebase)**:
  - When to use: For enforcing content safety policies in large language models.
  - How: Implements a structured guardrail with validation tasks like `evaluate_input_task`, policy enforcement through prompts, and output formatting using `PolicyEvaluation`.

## Key Concepts
- **AI Content Policy Enforcer**: A system that filters and controls AI outputs based on predefined rules.
- **PolicyEvaluation**: A Pydantic model for structuring compliance evaluation results.
- **Evaluate Input Task**: A task designed to validate user inputs against safety policies.

## Mental Models
- Use AI Content Policy Enforcer when you need a structured, multi-layered defense mechanism for your AI outputs.

## Anti-patterns
- Do not implement guardrails if you underestimate their effectiveness or fail to integrate them comprehensively into the system design.

## Code Examples
```python
# Example code demonstrating policy evaluation validation
def validate_policy_evaluation(output: Any) -> Tuple[bool, str, List[str]]:
    """Validates the raw string output from the LLM against strict safety guidelines."""
    logging.info(f"Raw LLM output received by evaluate_input_circuit: '{output}'")
    try:
        # If the output is a TaskOutput object, extract its pydantic content
        if isinstance(output, TaskOutput) and hasattr(output.pydantic):
            evaluation = output.pydantic
        else:
            evaluation = PolicyEvaluation.model_validate(data=output) 
    except Exception as e:
        logging.error(f"Guardrail FAILED: An unexpected error occurred during validation: {e}")
        return False, "Guardrail returned an unexpected output format."

    if evaluation.compliance_status not in ["compliant", "non-compliant"]:
        return False, f"Compliance status must be 'compliant' or 'non-compliant'. Got: {evaluation.compliance_status}"
    
    # Perform logical checks on the validated data
    if not evaluation.evaluation_summary:
        return False, "Evaluation summary cannot be empty."
    if not isinstance(evaluation.triggered_policies, list):
        return False, "Triggered policies must be a list."
      
    logging.info(f"Guardrail PASSED for policy evaluation.")
    # If valid, return True along with the parsed evaluation object
    return True, evaluation, evaluation.triggered_policies
```

## Reference Tables
| Parameter | Type      | Description                                      |
|-----------|-----------|-------------------------------------------------|
| compliance_status | String | Denotes if AI output is compliant or non-compliant. |
| evaluation_summary | String | Brief explanation for the compliance status.    |
| triggered_policies | List of Strings | Policies that were flagged as violated.         |

## Key Takeaways
1. Prioritize implementing guardrails to ensure AI safety and ethical behavior.
2. Use structured frameworks like Gemini/Firebase to enforce content safety policies effectively.
3. Continuously monitor and retrain models to adapt to evolving risks.

## Connects To
- Chapter 17: Advanced Code Crew Example