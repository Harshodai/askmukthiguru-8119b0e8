import random

from app.pipeline.stages.glue_stages import _WARM_GREETINGS

print("Testing 10 greetings...")
for i in range(10):
    greeting = random.choice(_WARM_GREETINGS)
    if "Sri Preethaji" in greeting or "Sri Krishnaji" in greeting:
        print(f"FAILED on greeting {i + 1}: {greeting}")
    else:
        print(f"Passed {i + 1}")
