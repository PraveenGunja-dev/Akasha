from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

load_dotenv(override=True)

def get_llm():
    provider = os.getenv("AI_PROVIDER", "openrouter").lower()
    if provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            model_name=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
        )
    elif provider == "groq":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_base="https://api.groq.com/openai/v1",
            openai_api_key=os.getenv("AKASHA_AI_API_KEY"),
            model_name="llama-3.3-70b-versatile"
        )
    elif provider == "azure":
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_base=os.getenv("OLLAMA_ENDPOINT", "http://192.168.0.59:11434/v1"),
            openai_api_key="ollama",
            model_name=os.getenv("OLLAMA_MODEL", "gemma4:latest")
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
