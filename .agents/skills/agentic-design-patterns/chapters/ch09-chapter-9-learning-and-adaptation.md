# Chapter 9: Learning and Adaptation

## Core Idea
Agents must learn and adapt by modifying their behavior based on experience to improve performance across diverse environments.

## Frameworks Introduced
- **Reinforcement Learning (RL)**:
  - When to use: When an agent interacts with an environment through actions, receives rewards or penalties, and aims to maximize cumulative reward.
  - How: Collect data, evaluate surrogate goal function using a special "clipped" objective function to ensure safety.

- **Proximal Policy Optimization (PPO)**:
  - When to use: For agents requiring stable, safe updates in environments with continuous action spaces.
  - How: Collect batch of experiences; optimize policy with clipped objective; clip ensures updates stay within known working range.

- **Direct Preference Optimization (DPO)**:
  - When to use: For agents aligning with human preferences without explicit reward functions.
  - How: Uses preference data directly, avoiding complex model training by linking preference data to optimal policies through mathematical relationships.

## Key Concepts
- **Reinforcement Learning**: An agent learns by interacting with an environment and receiving rewards or penalties based on actions taken. The goal is to maximize cumulative reward over time (Sutton & Barto, 2018).
  
- **Proximal Policy Optimization (PPO)**: A reinforcement learning algorithm that optimizes a policy in steps while ensuring updates remain within a known working range (Schulman et al., 2017).

- **Direct Preference Optimization (DPO)**: An alternative to using reward models, this method directly uses preference data from humans or systems to guide policy optimization without intermediate modeling (Robeyns et al., 2025).

## Mental Models
- The Self-Improving Coding Agent (SICA) is a system that autonomously improves its code through self-modifications based on past performance. It demonstrates how agents can evolve by implementing sub-agents, an overseer, and structured information flow.

## Anti-patterns
- **Rigid Training Paradigm**: Traditional training methods that do not allow for adaptability or recovery from unexpected issues (e.g., hardcoded rules without learning capabilities).

## Code Examples
```python
# Example code snippet: SICA's self-improvement mechanism in Python

from openevolve import OpenEvolve

# Initialize the system with initial program, evaluation file, and config
evolve = OpenEvolve(
    initial_program_path="path/to/initial_program.py",
    evaluation_file="path/to/evaluator.py",
    config_path="path/to/config.yaml"
)

# Run the evolution for 1000 iterations to find improved versions of the program
best_program = await evolve.run(iterations=1000)

# Print metrics of the best program found
print(f"Best program metrics:")
for name, value in best_program.metrics.items():
    print(f"  {name}: {value:.4f}")
```

This code demonstrates how SICA uses evolutionary algorithms to optimize programs by iteratively improving them based on evaluation results.

## Reference Tables
| Framework | Key Components and Application |
|----------|----------------------------------|
| PPO      | Collects data, evaluates surrogate goal function with clipping, ensures safe updates in continuous action spaces. |
| DPO      | Directly uses preference data to optimize policies without reward models, aligning agent behavior with human preferences. |

## Key Takeaways
1. Use reinforcement learning and proximal policy optimization for agents requiring stable, safe updates.
2. Leverage direct preference optimization when aligning agent behavior with human preferences is critical.
3. Implement modular systems with sub-agents, an overseer, and structured information flow to enhance performance in dynamic environments.

## Connects To
- Agent-based planning (Chapter 5)
- Multi-agent collaboration (Chapter 6)