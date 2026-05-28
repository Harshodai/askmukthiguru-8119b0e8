# Chapter 9: Embedding Native Functions Within Semantic Services

## Core Idea
This chapter demonstrates how to integrate custom native functions into semantic service layers, enabling AI agents and chatbots to access and utilize external APIs seamlessly through natural language interfaces.

### Frameworks Introduced
- **Semantic Kernel (SK)**: A high-level abstraction layer that allows embedding native or semantic functions within plugins, facilitating the creation of extensible AI services.
  
  - **When to use**: When you need to extend your AI capabilities with custom functionality while maintaining a clean and intuitive interface.
  - **How**: By defining native functions as plugins within the SK framework.

### Key Concepts
- **Semantic Service Layer**: A layer that wraps external API calls, providing them access to natural language interfaces.
  
  Example: The TMDB plugin allows users to ask questions like "give me list of currently playing movies for the action and comedy genres."
  
- **Kernel Arguments**: Parameters passed to functions within the semantic service layer.

### Mental Models
- Use SK when you need to extend your AI capabilities with custom functionality. Think of SK as a tool that lets you add features without modifying existing code.
  - Example: Adding a movie recommendation feature by integrating TMDB API calls into your chatbot's interface.

### Anti-patterns
- **Overcomplicating interactions**: Avoid creating complex interfaces when simple ones suffice to achieve the desired functionality.

## Code Examples
```python
tmdb.py
```  
```python
class TMDbService:
    def __init__(self):
        self.api_key = "your-TMDb-api-key"
    
    @kernel_function(description="Gets movie genre ID", name="get_movie_genre_id")
    def get_movie_genre_id(self, genre_name: str) -> str:
        print_function_call()
        base_url = "https://api.themoviedb.org/3"
        endpoint = f"{base_url}/genre/movie/list?api_key={self.api_key}&language=en-US"
        response = requests.get(endpoint)
        if response.status_code == 200:
            genres = response.json()['genres']
            for genre in genres:
                if genre_name.lower() in genre['name'].lower():
                    return str(genre['id'])
        return None
```

### Reference Tables
| Framework | Description |
|----------|-------------|
| SK (Semantic Kernel) | A framework that abstracts API calls and services, enabling their integration into natural language interfaces. |

## Key Takeaways
1. Use SK to embed native functions within semantic service layers for seamless access to external APIs.
2. Leverage the kernel function decorator to define custom functionality with clear descriptions and names.
3. Ensure proper registration of plugins to integrate them into your AI system effectively.

## Connects To
- **Chapter 5**: Covers creating new semantic skills, providing a foundation for understanding how to build custom AI capabilities.
- **Chapter 6**: Discusses extending semantic functions within plugins, building on the concepts introduced here.

By following this chapter, you can enhance your AI systems with custom functionality while maintaining a clean and intuitive interface.