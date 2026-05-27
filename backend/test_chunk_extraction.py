import asyncio
import logging

from app.config import settings
from services.sarvam_service import SarvamCloudService

logging.basicConfig(level=logging.INFO)

# The exact system and user prompts used by LightRAG for entity extraction
system_prompt = """---Role---
You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text.

---Instructions---
1.  **Entity Extraction & Output:**
    *   **Identification:** Identify clearly defined and meaningful entities in the input text.
    *   **Entity Details:** For each identified entity, extract the following information:
        *   `entity_name`: The name of the entity. If the entity name is case-insensitive, capitalize the first letter of each significant word (title case). Ensure **consistent naming** across the entire extraction process.
        *   `entity_type`: Categorize the entity using one of the following types: ["Person", "Location", "Organization", "Event", "Concept", "Method", "Artifact"]. If none apply, classify as `Other`.
        *   `entity_description`: Provide a concise yet comprehensive description of the entity's attributes and activities, based *solely* on the information present in the input text.
    *   **Output Format - Entities:** Output a total of 4 fields for each entity, delimited by "<|#|>", on a single line. The first field *must* be the literal string `entity`.
        *   Format: `entity<|#|>entity_name<|#|>entity_type<|#|>entity_description`

2.  **Relationship Extraction & Output:**
    *   **Identification:** Identify direct, clearly stated, and meaningful relationships between previously extracted entities.
    *   **N-ary Relationship Decomposition:** If a single statement describes a relationship involving more than two entities, decompose it into multiple binary relationship pairs.
    *   **Relationship Details:** For each binary relationship, extract the following fields:
        *   `source_entity`: The name of the source entity. Ensure **consistent naming** with entity extraction.
        *   `target_entity`: The name of the target entity. Ensure **consistent naming** with entity extraction.
        *   `relationship_keywords`: One or more high-level keywords summarizing the overarching nature, concepts, or themes of the relationship. Multiple keywords must be separated by a comma `,`.
        *   `relationship_description`: A concise explanation of the nature of the relationship.
    *   **Output Format - Relationships:** Output a total of 5 fields for each relationship, delimited by "<|#|>", on a single line. The first field *must* be the literal string `relation`.
        *   Format: `relation<|#|>source_entity<|#|>target_entity<|#|>relationship_keywords<|#|>relationship_description`

3.  **Delimiter Usage Protocol:**
    *   The "<|#|>" is a complete, atomic marker and must not be filled with content.

4.  **Completion Signal:** Output the literal string "<|COMPLETE|>" only after all entities and relationships, following all criteria, have been completely extracted and outputted.

---Examples---
[Source: The_Four_Sacred_Secrets.pdf | Chapter: Introduction]
Alex and Jordan share a commitment to discovery, which contrasts with Cruz's vision of control and order.
entity<|#|>Alex<|#|>person<|#|>Alex is a character who experiences frustration and is observant of the dynamics.
entity<|#|>Jordan<|#|>person<|#|>Jordan shares a commitment to discovery and has a significant interaction with Taylor.
relation<|#|>Alex<|#|>Jordan<|#|>shared goals, rebellion<|#|>Alex and Jordan share a commitment to discovery.
<|COMPLETE|>
"""

user_prompt = """---Task---
Extract entities and relationships from the input text in Data to be Processed below.

---Data to be Processed---
<Input Text>
```
The first secret is to live in a beautiful state. A beautiful state is a state of connection, peace, joy, and compassion. When you live in a beautiful state, your decisions are wise, your relationships are harmonious, and your actions are powerful. In contrast, suffering states are states of anger, fear, anxiety, and sadness. Suffering states narrow your perception and lead to destructive actions. Sri Preethaji and Sri Krishnaji teach that the transition from suffering states to beautiful states is the ultimate journey of human consciousness.
```

<Output>
"""


async def main():
    if not settings.sarvam_api_key:
        print("Error: SARVAM_API_KEY is not set in settings or .env file.")
        return
    service = SarvamCloudService()
    # Temporarily set gen_model to sarvam-m for the test
    service._gen_model = "sarvam-m"

    print("\n--- Testing Entity Extraction with 1500-char spiritual chunk ---")
    try:
        res = await service.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,  # Invalid for sarvam-m (2048 max), should self-heal!
        )
        print("\n=== Result ===")
        print(res)
    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    asyncio.run(main())
