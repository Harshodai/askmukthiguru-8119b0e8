# Chapter 60: 2. Graphs

## Core Idea
The chapter focuses on extracting meaningful insights from charts, graphs, and diagrams by converting them into text and analyzing their content to identify trends, patterns, or relationships.

## Frameworks Introduced
- **pdf2image**: A tool used for converting PDF files into image formats (PDF → images).
  - When to use: For preprocessing PDF documents before analysis.
  - How: Convert each page of the PDF using `convertor = convert_from_path('./TSLA-Q3-2023-Update-3.pdf')` and saving images as PNG files.

## Key Concepts
- **Payload**: A structured format (JSON) used to communicate requests to AI models, including content types like text or images.
  - Example: `{
    "model": "gpt-4-turbo",
    "messages": [
      {
        "role": "user",
        "content": "You are an assistant that find charts, graphs, or diagrams and summarize their information. ignore tables."
      }
    ]
  }`

## Mental Models
- Use **pdf2image** when you need to preprocess PDFs into images for analysis.
  - Think of pdf2image as a tool for preparing data before feeding it into AI models.

## Anti-patterns
- **Improper preprocessing**: Not converting images to text or encoding them correctly can lead to missed insights or inconsistent results.

## Code Examples
```python
from pdf2image import convert_from_path  

# Convert each page of the PDF to a PNG file
pages_png = [file for file in os.listdir("./pages") if file.endswith('.png')]

# Define the OpenAI API headers and payload structure
headers = {"Content-Type": "application/json"}
payload = {
    "model": "gpt-4-turbo",
    "messages": [
        {"role": "user", "content": "You are an assistant that find charts, graphs, or diagrams and summarize their information. ignore tables."}
    ],
    "max_tokens": 1000
}

# Function to encode images into base64 format for payload construction
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# Process each page and construct the request payload
for idx, page in enumerate(pages_png):
    # Get the base64 string for the current image
    base64_image = encode_image(f"./pages/{page}")
    
    # Adjust the payload to include the encoded image
    tmp_payload = copy.deepcopy(payload)
    tmp_payload["messages"][0]["content"].append({
        "type": "image_url",
        "image_url": f"data:image/png;base64,{base64_image}"
    })
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=tmp_payload)
        response.raise_for_status()
        graph_data = json.loads(response.content.decode('utf-8'))["choices"][0]["message"]["content"]
        
        # Construct the final description for storage
        desc = f"[Element] {graph_data}"
        graphs_description.append(desc)
    except Exception as e:
        print(f"Skipping page {idx} due to error: {str(e)}")
```

## Reference Tables
| Parameter          | Value/Implementation                                      |
|--------------------|----------------------------------------------------------|
| OpenAI API Model   | gpt-4-turbo                                               |
| Max Tokens         | 1000                                                      |
| PDF to Image Tool   | pdf2image                                                  |

## Key Takeaways
1. Proper preprocessing of PDFs into images is crucial for accurate analysis.
2. Structuring requests with JSON payloads ensures consistent and reliable information extraction from AI models.
3. Using tools like `pdf2image` streamlines the process of converting documents into a usable format.

This chapter emphasizes the importance of effective data preprocessing and structured request formulation to extract meaningful insights from visual data using modern AI capabilities.