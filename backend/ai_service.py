from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

load_dotenv()
provider = os.getenv("AI_PROVIDER", "ollama").lower()

def get_llm():
    if provider == "azure":
        # Placeholder for Azure initialization if this file is ever used.
        # Currently, the application uses call_azure_openai_curl in routers/ai.py
        raise NotImplementedError("Azure LLM is handled directly in routers/ai.py")
    else:
        from langchain_community.chat_models import ChatOpenAI
        return ChatOpenAI(
            openai_api_base=os.getenv("OLLAMA_ENDPOINT", "http://192.168.0.56:11434/v1"),
            openai_api_key="ollama",
            model_name=os.getenv("OLLAMA_MODEL", "llama3")
        )

def ask_llm(question: str, context: str = "") -> str:
    """
    Sends a prompt to the configured LLM and returns the response.
    """
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are the Akasha AI, an expert project intelligence assistant. Use the following context to answer if provided: {context}"),
        ("human", "{question}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"context": context, "question": question})
    return response.content
