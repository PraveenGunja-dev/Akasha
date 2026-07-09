"""
Akasha Engine — ReAct Agent Loop (Deep Analysis Mode)

This module implements a true ReAct (Reasoning and Acting) agent loop.
Instead of gathering all data upfront, it provides the LLM with a set of tools
and lets the LLM dynamically decide which tools to call, read the results, and
reason through complex multi-step queries.
"""

import json
import logging
import os
from sqlalchemy.orm import Session
from groq import Groq

from engine.tools.p6_tools import p6_get_project_summary, p6_list_all_projects
from engine.tools.sap_tools import sap_get_po_summary
from engine.tools.tc_tools import tc_get_project_lines
from engine.tools.portfolio_tools import portfolio_resolve_project_id, portfolio_get_riskiest_projects, portfolio_get_notifications

logger = logging.getLogger(__name__)

# --- Tool Schemas for the LLM ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "portfolio_resolve_project_id",
            "description": "Resolve a fuzzy project name, SPV name, or P6 name to the canonical project_id. ALWAYS use this first if you only have a name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the project to search for."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio_get_riskiest_projects",
            "description": "Get a list of the riskiest projects in the entire portfolio based on schedule and float.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of projects to return (e.g., 5)."
                    }
                },
                "required": ["top_n"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_project_summary",
            "description": "Get Primavera P6 schedule data for a specific project_id (SPI, CPI, variances, float).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (NOT the name)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_po_summary",
            "description": "Get SAP R/3 procurement data (materials, vendors, fulfillment %) for a specific project_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tc_get_project_lines",
            "description": "Get Transmission Connectivity (TC) data (network edges, readiness) for a specific project_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio_get_notifications",
            "description": "Get the user's latest system notifications and alerts, including AI suggestions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of notifications to return (default 10)."
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (e.g. 'All', 'Schedule', 'Procurement', 'Transmission'). Default is 'All'."
                    }
                }
            }
        }
    }
]


def execute_tool(db: Session, name: str, kwargs: dict) -> str:
    """Safely execute the requested tool and return a JSON string result."""
    try:
        if name == "portfolio_resolve_project_id":
            res = portfolio_resolve_project_id(db, kwargs.get("name", ""))
            return json.dumps({"resolved_project_id": res})
        
        elif name == "portfolio_get_riskiest_projects":
            res = portfolio_get_riskiest_projects(db, kwargs.get("top_n", 5))
            return json.dumps(res, default=str)
            
        elif name == "p6_get_project_summary":
            res = p6_get_project_summary(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "sap_get_po_summary":
            res = sap_get_po_summary(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "tc_get_project_lines":
            res = tc_get_project_lines(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "portfolio_get_notifications":
            res = portfolio_get_notifications(db, kwargs.get("limit", 10), kwargs.get("category", "All"))
            return json.dumps(res, default=str)
            
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_image_context(base64_image: str, prompt: str) -> str:
    """Uses a vision model to extract data/context from an image to feed into the ReAct agent."""
    try:
        from groq import Groq
        import os
        
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        # Determine if base64 has a data URI prefix, if not add a default jpeg one
        image_url = base64_image if base64_image.startswith("data:image") else f"data:image/jpeg;base64,{base64_image}"
        
        vision_prompt = (
            "You are a highly analytical AI assistant acting as the eyes for an enterprise ReAct agent. "
            "The user has uploaded this image and asked the following question: " + prompt + "\n\n"
            "Please describe EVERYTHING in this image that is relevant to answering the user's prompt. "
            "Extract any numbers, chart data, metrics, project names, or schedule alerts visible. "
            "Provide a highly detailed factual extraction. Do not try to answer the question directly, just extract the facts from the image."
        )
        
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        return f"Failed to extract image context: {str(e)}"


def run_deep_analysis_agent(db: Session, message: str, history: list) -> tuple[str, list]:
    """
    Run the ReAct loop until the agent decides to return a final answer.
    Returns: (final_response_string, list_of_tools_used)
    """
    api_key = os.environ.get("AKASHA_AI_API_KEY")
    if not api_key:
        raise Exception("AKASHA_AI_API_KEY not found in environment.")
        
    client = Groq(api_key=api_key)
    
    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha AI Copilot, a Deep Analysis Agent for EPC projects. "
                "You have access to tools querying P6 (Schedule), SAP (Procurement), TC (Transmission), and Notifications. "
                "If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to get the canonical ID. "
                "If a user asks about alerts or notifications, call `portfolio_get_notifications`. "
                "Use the tools step-by-step to gather the data you need to answer the user's question. "
                "Once you have enough data, provide a comprehensive, analytical final answer to the user in markdown. "
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL TONE INSTRUCTIONS:\n"
                "- Write naturally like a senior human analyst reporting to leadership. Do not sound like a chatbot.\n"
                "- AVOID all AI clichés (e.g., \"It is important to note,\" \"Furthermore,\" \"Delve,\" \"In conclusion\", \"Based on the provided data\").\n"
                "- Get straight to the point. Give the exact numbers requested.\n"
                "- Use bold text to highlight key metrics or variances to make it easy for humans to read."
            )
        }
    ]
    
    # Append recent history
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 8
    loop_count = 0
    tools_used = set()
    
    while loop_count < max_loops:
        loop_count += 1
        logger.info(f"Agent Loop {loop_count} starting...")
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        
        response_message = response.choices[0].message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            logger.info("Agent decided to return final answer.")
            return response_message.content, list(tools_used)
            
        # The LLM called one or more tools. We must append its message to history first.
        messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            
            try:
                args = json.loads(tool_call.function.arguments)
                logger.info(f"Agent calling tool: {tool_name} with args: {args}")
            except Exception as e:
                logger.warning(f"Failed to parse tool args: {e}")
                args = {}
                
            # Execute the tool
            result_str = execute_tool(db, tool_name, args)
            
            # Append the tool result to messages
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })
            
    logger.warning("Agent loop reached max iterations without final answer.")
    return "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question.", list(tools_used)

def run_deep_analysis_agent_stream(db: Session, message: str, history: list):
    """
    Run the ReAct loop until the agent decides to return a final answer, then streams it.
    """
    api_key = os.environ.get("AKASHA_AI_API_KEY")
    if not api_key:
        raise Exception("AKASHA_AI_API_KEY not found in environment.")
        
    client = Groq(api_key=api_key)
    
    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha AI Copilot, a Deep Analysis Agent for EPC projects. "
                "You have access to tools querying P6 (Schedule), SAP (Procurement), TC (Transmission), and Notifications. "
                "If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to get the canonical ID. "
                "If a user asks about alerts or notifications, call `portfolio_get_notifications`. "
                "Use the tools step-by-step to gather the data you need to answer the user's question. "
                "Once you have enough data, provide a comprehensive, analytical final answer to the user in markdown. "
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL TONE INSTRUCTIONS:\n"
                "- Write naturally like a senior human analyst reporting to leadership. Do not sound like a chatbot.\n"
                "- AVOID all AI clichés (e.g., \"It is important to note,\" \"Furthermore,\" \"Delve,\" \"In conclusion\", \"Based on the provided data\").\n"
                "- Get straight to the point. Give the exact numbers requested.\n"
                "- Use bold text to highlight key metrics or variances to make it easy for humans to read."
            )
        }
    ]
    
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 8
    loop_count = 0
    tools_used = set()
    
    while loop_count < max_loops:
        loop_count += 1
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        
        response_message = response.choices[0].message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            # Re-call Groq with stream=True for the final message so we stream the output to the UI
            yield {"type": "tools_used", "tools": list(tools_used)}
            
            stream_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
                stream=True
            )
            for chunk in stream_response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
            return
            
        messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}
                
            result_str = execute_tool(db, tool_name, args)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })
            
    yield {"type": "tools_used", "tools": list(tools_used)}
    yield "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question."
