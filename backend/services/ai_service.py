from langchain_core.prompts import ChatPromptTemplate
from engine.model_provider import get_model_provider

def get_llm():
    return get_model_provider().chat_model()

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
