# Chapter 6: Building a Portfolio of Projects that Shows Skill Progression

## Core Idea  
The chapter emphasizes using a portfolio approach to showcase skill progression over time by strategically selecting projects that align with learning objectives.

## Frameworks Introduced  
- **The 5 Whys**: A tool for digging deeper into root causes, often used to identify systemic issues in project management.  
  - When to use: To uncover underlying problems or failures in processes.  
  - How: Ask "Why" five times to get to the core issue.  

- **Value Stream Mapping**: A visual tool for analyzing workflows and identifying inefficiencies.  
  - When to use: To map out project processes and streamline operations.  
  - How: Identify inputs, processes, outputs, and stakeholders to optimize workflows.  

- **Agile Retrospectives**: A meeting where team members reflect on past iterations to improve future performance.  
  - When to use: After completing an Agile sprint to gather feedback and plan improvements.  
  - How: Focus on learning from outcomes, challenges, and opportunities.  

## Key Concepts  
- **Portfolio Mapping**: Organizing projects based on their value proposition, complexity, and alignment with goals.  
- **Value Proposition**: The unique benefit or outcome a project provides that justifies its existence.  
- **Progress Tracking**: Monitoring skill development and project outcomes to ensure measurable growth.  
- **Iterative Learning**: Using failed attempts as learning opportunities to refine skills over time.  

## Mental Models  
- Build projects to demonstrate growth when you want to showcase your evolving capabilities.  

## Anti-patterns  
- **Project Silos**: Avoid creating separate projects for different stakeholders, as they may conflict and limit learning.  
  - Why it fails: Limited collaboration and shared knowledge gaps.  

- **Matthew Effect**: Avoid giving credit to those who already have resources while neglecting others.  
  - Why it fails: Inequitable recognition of contributions and growth.  

## Code Examples  
```
import jira
from datetime import date

class ProjectTask:
    def __init__(self, project_name, task_description, due_date=None):
        self.project_name = project_name
        self.task_description = task_description
        self.due_date = due_date

    def add_task(self, priority_level):
        if not self.due_date or self.due_date <= date.today():
            raise ValueError("Task must have a valid due date.")
        jira.addIssue(
            issue_type="Task",
            project=self.project_name,
            title=self.task_description,
            labels=[f"Priority{'-' + str(priority_level)}"],
            summary=self.task_description,
            description=f"Description for {self.task_description} (Due: {self.due_date})",
            reporter=self.project_name
        )
```
- **What it demonstrates**: A system to track and prioritize tasks with due dates using Jira.  

## Reference Tables  
| Framework                | When to Use          | How                     |
|--------------------------|----------------------|-------------------------|
| The 5 Whys              | Uncovering root causes | Ask "Why" five times      |
| Value Stream Mapping    | Streamlining workflows | Map inputs, processes, outputs       |
| Agile Retrospectives     | After an Agile sprint | Reflect on outcomes and feedback |

## Key Takeaways  
1. Use portfolio mapping to organize projects by value proposition and track progress over time.  
2. Apply frameworks like The 5 Whys, Value Stream Mapping, and Agile retrospectives to identify and address systemic issues.  
3. Avoid anti-patterns such as project silos and the Matthew effect to ensure equitable learning opportunities.  

## Connects To  
- Relates to Chapter 4 on Project Management Principles for understanding workflows.  
- Connects with Chapter 5 on Learning and Adaptation for iterative skill development.