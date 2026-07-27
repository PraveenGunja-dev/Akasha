# Akasha Chatbot Enhancement Guide v2.1

> **Historical, inactive prototype:** This enhanced-orchestrator alternative is not registered as the production chatbot path. The integration steps below are archival and conditional, not current deployment instructions.

## Overview

This enhancement package significantly improves the Akasha Platform chatbot with:

✅ **Deep Data Understanding** - Semantic understanding of all metrics and data relationships  
✅ **Intelligent Responses** - Detailed, accurate answers with actionable insights  
✅ **Visualization Generation** - Automatic chart/graph generation (pie, bar, line, bubble)  
✅ **Advanced Intent Classification** - Better understanding of user queries  
✅ **Risk Intelligence** - Automatic risk detection and recommendations  
✅ **Portfolio Analysis** - Cross-project comparison and portfolio-level insights  

---

## New Modules

### 1. **Data Schema Module** (`engine/data_schema.py`)
Deep understanding of your data structures and metrics.

```python
from engine.data_schema import DataSchemaAnalyzer

analyzer = DataSchemaAnalyzer(db)

# Get comprehensive project context
context = analyzer.get_p6_project_context(project_id)
# Returns: {
#   "project_name": "...",
#   "overall_health": "HEALTHY|AT RISK|CRITICAL",
#   "schedule_metrics": {...},
#   "activity_breakdown": {...},
#   "schedule_analysis": {...},
#   "cost_analysis": {...},
#   "data_quality": {...}
# }

# Generate risk insights
insights = analyzer.generate_risk_insights(project_id)
# Returns: [{
#   "type": "SCHEDULE_RISK|COST_RISK|PROGRESS_RISK",
#   "severity": "HIGH|MEDIUM|LOW",
#   "insight": "...",
#   "recommendation": "..."
# }]

# Compare multiple projects
comparisons = analyzer.compare_projects([proj1, proj2, proj3])

# Get SAP procurement context
sap_context = analyzer.get_sap_procurement_context(project_id)
```

### 2. **Visualization Generator** (`engine/visualizations.py`)
Generates chart specifications for frontend rendering.

```python
from engine.visualizations import VisualizationGenerator

viz = VisualizationGenerator(db)

# Generate pie chart
pie_data = viz.generate_activity_status_pie(project_id)
# Returns Recharts-compatible pie chart spec with data

# Generate bar chart
bar_data = viz.generate_project_comparison_bar([proj1, proj2, proj3])

# Generate tables
table_data = viz.generate_critical_activities_table(project_id)

# Generate bubble chart (risk matrix)
bubble_data = viz.generate_portfolio_risk_bubble()

# List all available visualizations for a project
available = viz.get_available_visualizations(project_id)

# Generate any visualization by type
viz_data = viz.generate_visualization("activity_status_pie", project_id)
```

**Supported Chart Types:**
- `activity_status_pie` - Activity breakdown by status
- `budget_pie` - Spent vs remaining budget
- `project_comparison_bar` - Multi-project metrics comparison
- `milestones_bar` - Milestone progress
- `schedule_trend_line` - Schedule adherence over time
- `cumulative_cost_line` - Cost curve (planned vs actual)
- `critical_activities_table` - Critical path activities
- `material_status_table` - Material delivery gaps
- `portfolio_risk_bubble` - SPI vs CPI risk matrix

### 3. **Response Formatter** (`engine/response_formatter.py`)
Formats intelligent, detailed responses with insights and visualizations.

```python
from engine.response_formatter import IntelligentResponseFormatter

formatter = IntelligentResponseFormatter(db)

# Format project status response
response = formatter.format_project_status_response(project_id, question)
# Returns: {
#   "type": "project_status",
#   "answer": "Formatted narrative answer",
#   "health_status": "HEALTHY|AT RISK|CRITICAL",
#   "key_metrics": {...},
#   "insights": [...],
#   "suggested_visualizations": [...],
#   "data_quality": {...}
# }

# Format risk analysis
risk_response = formatter.format_risk_analysis_response(project_id)

# Format portfolio comparison
comp_response = formatter.format_portfolio_comparison([proj1, proj2])

# Format critical activities
critical_response = formatter.format_critical_activities_response(project_id)

# Format budget analysis
budget_response = formatter.format_budget_analysis_response(project_id)

# Determine if visualization is needed
should_viz = formatter.should_include_visualization("show me a pie chart")  # True/False
```

### 4. **Enhanced Orchestrator** (`engine/enhanced_orchestrator.py`)
Central hub that integrates all new capabilities.

```python
from engine.enhanced_orchestrator import EnhancedChatOrchestrator

orchestrator = EnhancedChatOrchestrator(db)

# Gather comprehensive project context
context = orchestrator.gather_comprehensive_project_context(project_id)

# Process different query types
factual_response = orchestrator.process_factual_query(message, project_id, context)
analytical_response = orchestrator.process_analytical_query(message, [proj1, proj2], context)
advisory_response = orchestrator.process_advisory_query(message, [proj1, proj2], context)

# Get available visualizations
viz_list = orchestrator.get_available_visualizations_for_project(project_id)

# Generate specific visualization
viz_data = orchestrator.generate_visualization("activity_status_pie", project_id)

# Export comprehensive analysis
export = orchestrator.export_project_analysis(project_id, format="json")
```

### 5. **Enhanced Intent Classifier v2** (`engine/intent_v2.py`)
Better understanding of user queries and intent.

```python
from engine.intent_v2 import EnhancedIntentClassifier

intent = EnhancedIntentClassifier.classify(
    message="Show me critical path activities for Project A",
    history=[...],
    project_names=[...]
)
# Returns: EnhancedChatIntent {
#   "intent_type": "visualization|factual|analytical|advisory",
#   "domains": ["p6", "sap", "tc"],
#   "is_portfolio": False,
#   "is_visualization_requested": True,
#   "requires_comparison": False,
#   "confidence": 0.95,
#   ...
# }

# Or use drop-in replacement for existing code
from engine.intent_v2 import enhanced_classify_intent
intent_dict = enhanced_classify_intent(message, history, project_names)
```

---

## Integration Steps

### Step 1: Update the AI Router

Edit `backend/routers/ai.py`:

```python
from engine.enhanced_orchestrator import EnhancedChatOrchestrator
from engine.intent_v2 import enhanced_classify_intent

@router.post("/chat-v2")
def chat_with_enhanced_copilot(req: ChatRequest, db: Session = Depends(get_db)):
    """New endpoint using enhanced chatbot with visualizations."""
    
    orchestrator = EnhancedChatOrchestrator(db)
    
    # Use enhanced intent classifier
    intent = enhanced_classify_intent(
        req.message,
        history=req.history,
        project_names=[req.projectId] if req.projectId else None
    )
    
    # Gather comprehensive context
    context = orchestrator.gather_comprehensive_project_context(
        req.projectId or intent.projects[0]
    )
    
    # Route based on intent type
    if intent["intent_type"] == "visualization":
        response = orchestrator.process_factual_query(
            req.message,
            req.projectId,
            context
        )
    elif intent["intent_type"] == "analytical":
        response = orchestrator.process_analytical_query(
            req.message,
            intent["projects"] or [req.projectId],
            context
        )
    elif intent["intent_type"] == "advisory":
        response = orchestrator.process_advisory_query(
            req.message,
            intent["projects"] or [req.projectId],
            context
        )
    else:
        response = orchestrator.process_factual_query(
            req.message,
            req.projectId,
            context
        )
    
    # Add metadata
    response = orchestrator.response_formatter.enrich_response_with_metadata(response)
    
    return response
```

### Step 2: Update Frontend Chat Interface

Your frontend chat component should handle:

1. **Text Responses** - Markdown formatted answer
2. **Visualizations** - Display chart specs using Recharts
3. **Insights** - Show risk/recommendation cards
4. **Metadata** - Display data quality and timestamp

Example frontend handling:

```typescript
// In your React component
const handleChatResponse = (response) => {
  // 1. Display answer
  setAnswer(response.answer);
  
  // 2. Display visualizations if present
  if (response.visualizations) {
    response.visualizations.forEach(viz => {
      displayChart(viz.type, viz.data);
    });
  }
  
  // 3. Display insights
  if (response.insights) {
    response.insights.forEach(insight => {
      displayInsight(insight);
    });
  }
  
  // 4. Display data quality
  if (response.data_quality) {
    showDataQualityIndicator(response.data_quality);
  }
};
```

---

## Example Use Cases

### Query 1: "What's the status of Project A?"
```
Intent: factual
Response includes:
- Narrative status with health indicator
- Key metrics (completion %, SPI, CPI)
- Activity status pie chart
- Data quality assessment
```

### Query 2: "Show me critical path activities"
```
Intent: visualization + factual
Response includes:
- Critical activities table
- Narrative explanation
- Activity status breakdown pie chart
- Risk recommendations
```

### Query 3: "Compare Project A vs Project B and show me which is riskier"
```
Intent: analytical + visualization
Response includes:
- Comparison narrative
- Portfolio comparison bar chart
- Risk matrix bubble chart
- Top risks for each project
- Recommendations
```

### Query 4: "What are the risks in my portfolio?"
```
Intent: advisory + portfolio
Response includes:
- Portfolio-level risk summary
- Ranked risks by severity
- Affected projects
- Actionable recommendations
- Suggested mitigation actions
```

### Query 5: "Generate a budget report for Project A"
```
Intent: advisory + visualization
Response includes:
- Budget analysis narrative
- Spent vs remaining budget pie chart
- Cost trend line chart (if historical data available)
- Cost performance analysis
- Budget recommendations
```

---

## Configuration & Customization

### Adjust Risk Thresholds

In `engine/data_schema.py`, modify these methods:

```python
def _interpret_float(self, total_float):
    # Adjust these thresholds based on your projects
    if total_float <= 0:
        return "CRITICAL"
    elif total_float <= 7:  # CHANGE THIS VALUE (days)
        return "TIGHT"
    # ...

def _determine_project_health(self, p6, activity_statuses):
    # Adjust risk scoring logic here
    risks = 0
    if p6.schedule_performance_index and p6.schedule_performance_index < 0.95:
        risks += 2  # CHANGE THIS WEIGHT
    # ...
```

### Add Custom Visualizations

In `engine/visualizations.py`:

```python
def generate_custom_visualization(self, project_id: str) -> Dict[str, Any]:
    """Add your custom chart here."""
    return {
        "type": "custom",
        "title": "Custom Title",
        "data": [...],
        # ... your data structure
    }
```

### Extend Data Schema Analysis

In `engine/data_schema.py`:

```python
def get_custom_metrics(self, project_id: str) -> dict:
    """Add custom metric calculations."""
    # Your logic here
    return {...}
```

---

## Response Structure

All enhanced responses follow this structure:

```json
{
  "type": "project_status|risk_analysis|portfolio_comparison|...",
  "answer": "Natural language response",
  "health_status": "HEALTHY|AT RISK|CRITICAL",
  "project_name": "...",
  "project_id": "...",
  "key_metrics": {...},
  "insights": [{
    "type": "SCHEDULE_RISK|COST_RISK|...",
    "severity": "HIGH|MEDIUM|LOW",
    "insight": "...",
    "recommendation": "..."
  }],
  "suggested_visualizations": [{
    "type": "activity_status_pie",
    "data": {...},
    "reason": "..."
  }],
  "data_quality": {
    "completeness_percentage": 95,
    "quality_rating": "EXCELLENT"
  },
  "generated_at": "2024-01-15T10:30:00Z",
  "version": "2.1"
}
```

---

## Performance Considerations

1. **Caching** - Use existing cache layer from `engine/cache.py`
2. **Database Queries** - Batch queries where possible
3. **Visualization Generation** - Pre-compute for common queries
4. **Response Size** - Compress visualizations for large datasets

Example optimization:

```python
# Check cache before analysis
freshness = check_freshness(db, project_id)
if not freshness["is_stale"]:
    cached = get_cached_data(db, project_id)
    return cached_formatter.format_response(cached)

# If stale, compute fresh
context = analyzer.get_p6_project_context(project_id)
update_cache(db, project_id, context)
return formatter.format_project_status_response(project_id, question)
```

---

## Testing

### Test Enhanced Intent Classification

```python
from engine.intent_v2 import EnhancedIntentClassifier

test_cases = [
    ("Show me critical path", "visualization"),
    ("What's status of Project A?", "factual"),
    ("Compare A vs B", "analytical"),
    ("What should I do?", "advisory"),
]

for question, expected_type in test_cases:
    intent = EnhancedIntentClassifier.classify(question)
    assert intent.intent_type == expected_type
    print(f"✓ {question} -> {intent.intent_type}")
```

### Test Data Analysis

```python
from engine.data_schema import DataSchemaAnalyzer

analyzer = DataSchemaAnalyzer(db)
context = analyzer.get_p6_project_context("PROJECT_ID")

# Verify all metrics are present
assert "project_name" in context
assert "overall_health" in context
assert "schedule_analysis" in context
print("✓ Data analysis complete")
```

### Test Visualization Generation

```python
from engine.visualizations import VisualizationGenerator

viz = VisualizationGenerator(db)
chart = viz.generate_activity_status_pie("PROJECT_ID")

assert chart["type"] == "pie"
assert "data" in chart
assert len(chart["data"]) > 0
print("✓ Visualization generated successfully")
```

---

## Troubleshooting

**Q: Visualizations not showing?**  
A: Ensure frontend is expecting the `visualizations` array in response.

**Q: Data quality is low?**  
A: Check that P6 data is being synced. Use `data_quality` field to identify missing metrics.

**Q: Responses too generic?**  
A: Increase confidence thresholds in `EnhancedIntentClassifier` or adjust analyzer logic.

**Q: Performance issues?**  
A: Enable caching and consider materialized views for expensive queries.

---

## Archived Conditional Next Steps

1. Conditionally load new modules in an isolated test backend after approval
2. ✅ Update AI router with v2 endpoint
3. ✅ Update frontend to handle visualizations
4. ✅ Test with real project data
5. ✅ Monitor response accuracy and adjust thresholds
6. ✅ Collect user feedback and iterate

---

## Support & Maintenance

- Modules are prototypes; production readiness was not validated
- Backward compatible with existing orchestrator
- Can run v1 and v2 simultaneously during transition
- Comprehensive error handling included

---

**Version:** 2.1  
**Updated:** 2026-07-22  
**Status:** Inactive historical prototype; not integrated or production-ready
