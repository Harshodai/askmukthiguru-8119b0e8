# Chapter 6: Setting Up Your Machine Learning Environment

## Core Idea
This chapter teaches you to establish a controlled environment for machine learning projects using virtual environments and pip, ensuring consistent dependencies.

## Frameworks Introduced
- **Virtual Environment**: Created with `python -m venv my_venv_name .` and activated with `source my_venv_name/bin/activate`.
  - When to use: For project-specific isolated environments.
  - How: Activate after creating the environment, then install dependencies.

## Key Concepts
- **Virtual Environment**: Ensures consistent package versions across projects.
- **pip**: Manages Python package installations and versions.
- **Google Colab**: A cloud-based Jupyter notebook for accelerated ML/DL training with GPUs/TPUs.
- **.env File**: Stores API keys securely in a text file on Google Drive.

## Mental Models
- Use virtual environments when you need project-specific dependencies, as they isolate your project's setup from others.

## Anti-patterns
- **Not specifying versions**: Fails because it can lead to dependency conflicts or unexpected behavior if packages are updated.

## Code Examples
```python
# Example: Installing packages in a Colab notebook
pip install transformers==4.32.0 numpy==1.23.5

# Example: Handling API keys with .env files
OPENAI_API_KEY=your_openai_key
```
- **What it demonstrates**: Efficiently managing dependencies and securely storing API credentials.

## Reference Tables

| Package       | Version |
|---------------|---------|
| deeplake      | 3.6.19  |
| openai        | 0.27.8  |
| tiktoken      | 0.4.0   |
| transformers  | 4.32.0  |
| torch         | 2.0.1   |
| numpy          | 1.23.5  |
| deepspeed     | 0.10.1  |
| trl            | 0.7.1   |
| peft           | 0.5.0   |
| wandb         | 0.15.8  |
| bitsandbytes   | 0.41.1  |
| accelerate    | 0.22.0  |
| tqdm           | 4.66.1  |
| neural_compressor | 2.2.1  |
| onnx            | 1.14.1  |
| pandas        | 2.0.3   |
| scipy          | 1.11.2  |

## Key Takeaways
1. Use virtual environments to manage project dependencies.
2. Install exact versions of libraries as specified in the requirements.txt file.
3. Securely store API keys in a .env file on Google Drive.

## Connects To
- Relates to chapters on machine learning basics and deployment strategies.