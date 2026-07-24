"""
Akasha Chatbot Enhancement - Implementation Examples

This file provides ready-to-use code snippets for integrating the enhanced
chatbot modules into your existing FastAPI router.
"""

# ============================================
# EXAMPLE 1: Update AI Router with V2 Endpoint
# ============================================

"""
Replace this section in backend/routers/ai.py:

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from database import get_db
import models

# NEW IMPORTS
from engine.enhanced_orchestrator import EnhancedChatOrchestrator
from engine.intent_v2 import enhanced_classify_intent
from engine.visualizations import VisualizationGenerator

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []
    projectId: Optional[str] = None
    sessionId: Optional[str] = None
    isDeepAnalysis: bool = False


@router.post("/chat-v2")
def enhanced_chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    '''Enhanced chat endpoint with visualizations and intelligence.'''
    
    session_id = req.sessionId or str(uuid.uuid4())
    
    try:
        # 1. Initialize enhanced orchestrator
        orchestrator = EnhancedChatOrchestrator(db)
        
        # 2. Classify intent with enhanced classifier
        intent = enhanced_classify_intent(
            message=req.message,
            history=req.history,
            project_names=[req.projectId] if req.projectId else None
        )
        
        # 3. Gather comprehensive context
        project_id = req.projectId or (intent["projects"][0] if intent["projects"] else None)
        
        if project_id:
            context = orchestrator.gather_comprehensive_project_context(project_id)
        else:
            context = {}
        
        # 4. Route based on intent type
        response = {}
        
        if intent["intent_type"] == "visualization":
            response = orchestrator.process_factual_query(
                req.message,
                project_id,
                context
            )
        
        elif intent["intent_type"] == "analytical":
            projects_to_analyze = intent["projects"] or [project_id] if project_id else []
            response = orchestrator.process_analytical_query(
                req.message,
                projects_to_analyze,
                context
            )
        
        elif intent["intent_type"] == "advisory":
            projects_to_advise = intent["projects"] or [project_id] if project_id else []
            response = orchestrator.process_advisory_query(
                req.message,
                projects_to_advise,
                context
            )
        
        else:  # factual
            response = orchestrator.process_factual_query(
                req.message,
                project_id,
                context
            )
        
        # 5. Add metadata and enrich response
        response = orchestrator.response_formatter.enrich_response_with_metadata(response)
        response["session_id"] = session_id
        response["intent_detected"] = intent
        
        # 6. Save to conversation history
        db_session = db.query(models.ChatSession).filter_by(session_id=session_id).first()
        if not db_session:
            db_session = models.ChatSession(
                session_id=session_id,
                title=req.message[:50]
            )
            db.add(db_session)
            db.commit()
            db.refresh(db_session)
        
        user_msg = models.ChatMessage(
            session_id=session_id,
            role="user",
            content=req.message
        )
        
        assistant_msg = models.ChatMessage(
            session_id=session_id,
            role="assistant",
            content=response.get("answer", ""),
            metadata=response
        )
        
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        
        return response
    
    except Exception as e:
        logger.error(f"Error in enhanced chat: {str(e)}")
        return {
            "error": str(e),
            "answer": "An error occurred processing your question.",
            "type": "error"
        }


@router.get("/visualizations/{project_id}")
def get_available_visualizations(project_id: str, db: Session = Depends(get_db)):
    '''List available visualizations for a project.'''
    
    orchestrator = EnhancedChatOrchestrator(db)
    viz_list = orchestrator.get_available_visualizations_for_project(project_id)
    
    return {
        "project_id": project_id,
        "visualizations": viz_list
    }


@router.post("/visualization")
def generate_visualization(
    project_id: str,
    chart_type: str,
    db: Session = Depends(get_db)
):
    '''Generate a specific visualization.'''
    
    orchestrator = EnhancedChatOrchestrator(db)
    viz_data = orchestrator.generate_visualization(chart_type, project_id)
    
    return {
        "chart_type": chart_type,
        "project_id": project_id,
        "data": viz_data
    }


@router.get("/project-analysis/{project_id}")
def export_project_analysis(
    project_id: str,
    format: str = "json",
    db: Session = Depends(get_db)
):
    '''Export comprehensive project analysis.'''
    
    orchestrator = EnhancedChatOrchestrator(db)
    export = orchestrator.export_project_analysis(project_id, format)
    
    return export
"""

# ============================================
# EXAMPLE 2: Frontend React Component
# ============================================

"""
Example React component to display enhanced chatbot responses:

import React, { useState } from 'react';
import { PieChart, BarChart, LineChart, ResponsiveContainer, Pie, Bar, Line } from 'recharts';

export const EnhancedChatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    try {
      const response = await fetch('/api/chat-v2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          history: messages,
          projectId: localStorage.getItem('selectedProject')
        })
      });

      const data = await response.json();
      
      // Add messages
      setMessages([
        ...messages,
        { role: 'user', content: input },
        { role: 'assistant', content: data }
      ]);
      
      setInput('');
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const renderVisualization = (viz) => {
    if (viz.type === 'pie' && viz.data?.data) {
      return (
        <div className="mt-4 w-full h-80">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={viz.data.data}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      );
    }
    
    if (viz.type === 'bar' && viz.data?.data) {
      return (
        <div className="mt-4 w-full h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={viz.data.data}>
              <Bar dataKey="completion" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      );
    }
    
    if (viz.type === 'table' && viz.data?.rows) {
      return (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse border border-gray-300">
            <thead className="bg-gray-200">
              {viz.data.columns?.map((col) => (
                <th key={col.key} className="border p-2 text-left">
                  {col.label}
                </th>
              ))}
            </thead>
            <tbody>
              {viz.data.rows?.map((row, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  {viz.data.columns?.map((col) => (
                    <td key={col.key} className="border p-2">
                      {row[col.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    
    return null;
  };

  const renderInsight = (insight) => {
    const severityColors = {
      'HIGH': 'bg-red-100 border-red-300',
      'MEDIUM': 'bg-yellow-100 border-yellow-300',
      'LOW': 'bg-blue-100 border-blue-300'
    };
    
    return (
      <div className={`mt-2 p-3 border-l-4 rounded ${severityColors[insight.severity]}`}>
        <strong>{insight.type}</strong> ({insight.severity})
        <p className="text-sm mt-1">{insight.insight}</p>
        <p className="text-xs text-gray-600 mt-1">→ {insight.recommendation}</p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={msg.role === 'user' ? 'text-right' : 'text-left'}>
            <div
              className={
                msg.role === 'user'
                  ? 'inline-block bg-blue-500 text-white p-3 rounded-lg max-w-lg'
                  : 'inline-block bg-gray-200 p-3 rounded-lg max-w-2xl'
              }
            >
              {typeof msg.content === 'string' ? (
                <p>{msg.content}</p>
              ) : (
                <>
                  <div className="prose max-w-none">
                    {msg.content.answer && (
                      <div
                        dangerouslySetInnerHTML={{
                          __html: msg.content.answer.replace(/\\n/g, '<br/>')
                        }}
                      />
                    )}
                  </div>
                  
                  {/* Health Status Badge */}
                  {msg.content.health_status && (
                    <div className="mt-3 text-sm font-semibold">
                      Status: {msg.content.health_status}
                    </div>
                  )}
                  
                  {/* Insights */}
                  {msg.content.insights?.length > 0 && (
                    <div className="mt-3">
                      <strong>Insights & Risks:</strong>
                      {msg.content.insights.map((insight, i) =>
                        renderInsight(insight)
                      )}
                    </div>
                  )}
                  
                  {/* Visualizations */}
                  {msg.content.visualizations?.length > 0 && (
                    <div className="mt-3">
                      {msg.content.visualizations.map((viz, i) =>
                        renderVisualization(viz)
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        {loading && <div>Generating response...</div>}
      </div>

      <form onSubmit={handleSendMessage} className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about project status, risks, budget..."
            className="flex-1 border rounded px-3 py-2"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
};
"""

# ============================================
# EXAMPLE 3: Database Models for Chat Storage
# ============================================

"""
Add to backend/models.py:

class ChatSession(Base):
    __tablename__ = "chat_session"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_message"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("chat_session.session_id"))
    role = Column(String)  # "user" or "assistant"
    content = Column(String)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("ChatSession", back_populates="messages")
"""

# ============================================
# EXAMPLE 4: Testing Enhanced Chatbot
# ============================================

"""
Test file: backend/tests/test_enhanced_chatbot.py

import pytest
from sqlalchemy.orm import Session
from engine.intent_v2 import EnhancedIntentClassifier
from engine.data_schema import DataSchemaAnalyzer
from engine.visualizations import VisualizationGenerator
from engine.response_formatter import IntelligentResponseFormatter
from engine.enhanced_orchestrator import EnhancedChatOrchestrator


def test_intent_classification():
    '''Test enhanced intent classifier'''
    
    test_cases = [
        ("Show me critical path", "visualization"),
        ("What's the status?", "factual"),
        ("Compare A vs B", "analytical"),
        ("What should I do?", "advisory"),
    ]
    
    for message, expected_type in test_cases:
        intent = EnhancedIntentClassifier.classify(message)
        assert intent.intent_type == expected_type


def test_data_schema_analysis(db_session: Session):
    '''Test data schema analyzer'''
    
    analyzer = DataSchemaAnalyzer(db_session)
    
    # Get P6 context
    context = analyzer.get_p6_project_context("PROJ-001")
    
    assert "project_name" in context
    assert "overall_health" in context
    assert "schedule_analysis" in context
    assert "cost_analysis" in context


def test_visualization_generation(db_session: Session):
    '''Test visualization generator'''
    
    viz = VisualizationGenerator(db_session)
    
    # Generate pie chart
    pie = viz.generate_activity_status_pie("PROJ-001")
    assert pie["type"] == "pie"
    assert "data" in pie
    
    # Generate bar chart
    bar = viz.generate_project_comparison_bar(["PROJ-001", "PROJ-002"])
    assert bar["type"] == "bar"


def test_response_formatting(db_session: Session):
    '''Test response formatter'''
    
    formatter = IntelligentResponseFormatter(db_session)
    
    response = formatter.format_project_status_response("PROJ-001", "What's the status?")
    
    assert "answer" in response
    assert "health_status" in response
    assert "insights" in response
    assert "suggested_visualizations" in response


def test_orchestrator_integration(db_session: Session):
    '''Test enhanced orchestrator'''
    
    orchestrator = EnhancedChatOrchestrator(db_session)
    
    # Test context gathering
    context = orchestrator.gather_comprehensive_project_context("PROJ-001")
    assert context.get("p6")
    
    # Test visualization list
    viz_list = orchestrator.get_available_visualizations_for_project("PROJ-001")
    assert len(viz_list) > 0
"""

# ============================================
# EXAMPLE 5: Configuration & Thresholds
# ============================================

"""
Create backend/config.py:

class ChatbotConfig:
    '''Configuration for enhanced chatbot thresholds and behavior.'''
    
    # Schedule Performance Index thresholds
    SPI_CRITICAL = 0.90  # Below 90% = behind schedule
    SPI_WARNING = 0.95   # Below 95% = watch
    
    # Cost Performance Index thresholds
    CPI_CRITICAL = 0.90  # Below 90% = overspend
    CPI_WARNING = 0.95   # Below 95% = watch
    
    # Float thresholds (in days)
    FLOAT_CRITICAL = 0        # 0 = critical path
    FLOAT_TIGHT = 7           # < 7 days = tight
    FLOAT_MODERATE = 30       # < 30 days = moderate
    
    # Activity completion thresholds
    COMPLETION_AT_RISK = 25   # Below 25% completed = at risk
    
    # Visualization limits
    MAX_CRITICAL_ACTIVITIES = 20
    MAX_COMPARISON_PROJECTS = 10
    MAX_TRENDS_POINTS = 50
    
    # Response configuration
    INCLUDE_DATA_QUALITY = True
    INCLUDE_INSIGHTS = True
    INCLUDE_VISUALIZATIONS = True
    MAX_INSIGHTS_PER_RESPONSE = 5
    
    # Caching
    CACHE_TTL_SECONDS = 300  # 5 minutes
    USE_HOT_CACHE = True


# Usage in your code:
from config import ChatbotConfig

if project_spi < ChatbotConfig.SPI_CRITICAL:
    risk_level = "CRITICAL"
"""

print("✓ All implementation examples provided")
print("✓ Ready for integration into your codebase")
