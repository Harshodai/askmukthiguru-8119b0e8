
import gradio as gr
from app.dependencies import get_container
from rag.graph import create_initial_state
import asyncio

async def chat_fn(message, history):
    """
    Gradio chat function.
    """
    container = get_container()
    
    # Create distinct chat history for LangGraph
    # history is list of [user_msg, bot_msg] lists
    graph_history = []
    for user_h, bot_h in history:
        graph_history.append({"role": "user", "content": user_h})
        graph_history.append({"role": "assistant", "content": bot_h})
        
    initial_state = create_initial_state(
        question=message,
        chat_history=graph_history,
        meditation_step=0 
    )
    
    try:
        result = await container.rag_graph.ainvoke(initial_state)
        response = result.get("final_answer", "Error generating response.")
    except Exception as e:
        response = f"Error: {e}"
        
    return response

def create_demo():
    custom_css = """
    #chatbot {min_height: 500px;}
    """
    
    with gr.Blocks(css=custom_css, title="Mukthi Guru") as demo:
        gr.Markdown("# 🕉️ Mukthi Guru")
        gr.Markdown("Conversational AI based on the teachings of Sri Preethaji & Sri Krishnaji.")
        
        chatbot = gr.Chatbot(elem_id="chatbot", type="messages")
        msg = gr.Textbox(placeholder="Ask a spiritual question...", show_label=False)
        clear = gr.ClearButton([msg, chatbot])

        async def respond(user_message, chat_history):
            bot_message = await chat_fn(user_message, chat_history)
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": bot_message})
            return "", chat_history

        msg.submit(respond, [msg, chatbot], [msg, chatbot])

    return demo
