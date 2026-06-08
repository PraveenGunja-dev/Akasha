import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing from environment variables.")

# Initialize the Groq LLM
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY, 
    model_name="openai/gpt-oss-120b"
)

def ask_groq(question: str, context: str = "") -> str:
    """
    Sends a prompt to the Groq LLM and returns the response.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are the Akasha AI, an expert project intelligence assistant. Use the following context to answer if provided: {context}"),
        ("human", "{question}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"context": context, "question": question})
    return response.content
