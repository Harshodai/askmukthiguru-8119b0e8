# Chapter 19: AAppendix AAccessing OpenAI large language models

## Core Idea
This chapter provides guidance on accessing OpenAI's API using API keys and explores alternative platforms like Azure OpenAI Studio for model access.

## Frameworks Introduced
- **Creating a Secret API Key**:  
  - When to use: When integrating with OpenAI services.  
  - How: Create a new key in the OpenAI platform, copy it securely, and use it for API requests.

## Key Concepts
- **API Key**: A unique string of characters used to authenticate access to OpenAI's models.
- **Azure OpenAI Studio**: An alternative platform hosted by Microsoft that provides access to OpenAI models via Azure resources.
- **Deployment**: Wrapping a model (e.g., GPT-4) in an Azure resource for access and management.

## Mental Models
- Use API keys when integrating with AI services like OpenAI or Azure OpenAI Studio.  
  - Think of API keys as the entry ticket to access and utilize AI models.

## Anti-patterns
- **Not keeping the key secure**: Failing to save the API key in a safe location can lead to unauthorized access.
- **Misconfiguring deployment details**: Incorrectly setting model names or base URLs can prevent successful API connections.

## Code Examples
```python
# Example: Creating an API Key in OpenAI
1. Go to the OpenAI platform and navigate to the left menu.
2. Select "API Keys" from the options.
3. Click "Create" to generate a new key.
4. Enter a name for the key (e.g., "GPT-Agents").
5. Click "Create Secret Key."
6. Copy the generated key to a secure location.

# Example: Configuring Azure OpenAI Studio
1. Log in to your Azure portal account subscription.
2. Create a new Azure OpenAI Studio resource in an appropriate region.
3. Deploy a model (e.g., GPT-4) within the deployment.
4. Access the deployment's endpoint, API key, and base URL for configuration.
```

## Reference Tables
| Parameter                | Value/Details                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| **API Key Usage**        | Used in requests to OpenAI or Azure OpenAI Studio resources.               |
| **Deployment Name**      | Represents the model name wrapped by an Azure deployment.                 |
| **Base URL**             | The endpoint where the deployed model is hosted, e.g., `https://api.openai.com`.

## Key Takeaways
1. Always keep your API key secure and use it only within its intended environment.
2. When using Azure OpenAI Studio, ensure you deploy models in regions with compatible versions.
3. If a model is unavailable through OpenAI or Azure, consider using open-source alternatives.

## Connects To
- Relates to chapter 2's discussion on integrating open-source LLMs into applications.