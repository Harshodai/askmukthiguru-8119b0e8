# Chapter 5: Adaptive Learning with AI

## Core Idea
This chapter explores how AI can enhance learning platforms by enabling personalized content generation, real-time feedback, and scalable curricula. It emphasizes leveraging large language models (LLMs) for creating and curating educational content while ensuring accuracy through human oversight.

---

## Frameworks Introduced

### 1. Offline Content Pipeline
- **Process**: 
  - **Lesson Generation Service**: Creates offline lessons using AI templates.
  - **Quality Control**: Human experts review and vet content for errors or safety.
  - **Storage**: Content is stored in a database for later delivery.

  - **When to use**: When creating new educational material from scratch.
  - **How**: 
    1. Generate questions using AI templates.
    2. Review for accuracy and relevance.
    3. Store validated content for distribution.

### 2. Online Serving Path
- **Process**:
  - **Lesson Curator Service**: Selects the most appropriate lessons from a curated bank based on user needs.
  - **Real-Time Delivery**: Instantly serves lessons to users after curation.
  - **Cache Refill**: Uses LPOP operations to pre-fetch content for faster access.

  - **When to use**: When providing personalized, real-time educational experiences.
  - **How**:
    1. Use prompts to select appropriate lessons from a pool.
    2. Pre-curate content using cache mechanisms.
    3. Serve curated content efficiently.

---

## Key Concepts

- **Lesson Generation**: Creates questions and answers using AI templates for offline content.
- **Lesson Curation**: Involves human experts reviewing and vetting educational material for quality.
- **Orchestrator Engine**: Manages prompts for LLMs to ensure accurate responses.
- **Model Router**: Selects appropriate models based on task requirements.

---

## Mental Models

1. **Use X when Y**:
   - Use LLMs for tasks requiring creative or conversational AI.
   - Use human experts for tasks requiring accuracy or safety checks.

2. **AI as a Double-Edged Sword**:
   - Leverage AI's power but ensure content quality through human oversight.

---

## Anti-patterns

1. **Without Quality Control**: Relying solely on AI can lead to errors or irrelevant content.
   - **What to avoid**: Ignoring human review of AI-generated content.

2. **Cold Path Issues**:
   - **What to avoid**: Over-reliance on real-time curation at the expense of pre-curation efficiency.

---

## Code Examples

### Lesson Generation Example
```python
from langchain.schema import QuestionAndAnswerSchema

async def generate_questions(
    skill_id: str,
    level: int,
    topic: str,
    template_id: str,
    context: Optional[str] = None
) -> List[QuestionAndAnswer]:
    """Generate questions based on the given parameters."""
    prompt = f"""Generate {5} multiple-choice questions about {topic} at skill level {level} for language {language}. Use template ID {template_id}.
    
    The questions should be in the format:
    Question: [Question]
    Answer: [Answer]
    Type: M
    Options: [Option1, Option2, Option3, Option4]"""
    
    response = await call_api(
        "generate_question",
        prompt=prompt,
        **context
    )
    
    return response.questions
```

### Curation Check Example
```python
def check_user_progress(user_id: str, lesson_history: List[LessonHistory]):
    """Check user progress and recent activity."""
    if not user_progress[user_id]:
        return False
    
    for lesson in user_progress[user_id][-3:]:  # Check last 3 lessons
        if lesson.graded:
            return True
            
    return False
```

---

## Reference Tables

### Parameter Table: Lesson Generation vs Curation
| **Parameter**          | **Offline (Lesson Generation)**                                      | **Online (Curation)**                                                |
|-------------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------|
|-------------------------|------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| Latency                | High (days)                                                               | Low (minutes)                                                          |
| Resource Usage           | High (AI generation capacity)                                             | Moderate (curation effort)                                               |
| Scalability            | Limited by AI models and context size                                         | High (efficient caching and parallel processing)                         |

### Decision Matrix: Choosing AI Models
| **Task Complexity**     | **Model Type Needed**              | **Examples of Models**                     |
|-------------------------|------------------------------------|--------------------------------------------|
| Simple                  | Small, fast, low-cost models         | Gemini 2.5, Claude 2                          |
| Medium                 | Medium-scale, reliable models       | GPT-3.5-turbo, Llama 2                       |
| Complex                | Large, enterprise-grade models     | Enterprise AI, custom models                  |

---

## Key Takeaways
1. Use AI for personalized lesson generation and curation.
2. Ensure content quality through human review and structured processes.
3. Leverage caching mechanisms for efficient online serving.
4. Choose appropriate AI models based on task requirements.

This chapter provides a framework for integrating AI into educational platforms while maintaining accuracy and scalability.