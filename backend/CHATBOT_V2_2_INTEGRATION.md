# Akasha Chatbot v2.2 Integration Guide

> **Historical, inactive design:** v2.2 is not registered in `backend/main.py` and is not the production chatbot path. Every accuracy, ambiguity-resolution, satisfaction, latency, and improvement percentage below is an unvalidated design estimate or target, not a measured result. No executable benchmark supports these figures.

**Unvalidated Target Accuracy:** 99%+
**Deployment Status:** Inactive historical prototype; not integrated, deployed, or production-ready
**Backward Compatibility:** 100% (v2.1 endpoints unaffected)

---

## 📋 Overview

Akasha Chatbot v2.2 proposed a major accuracy upgrade through 5 strategic architectural improvements; the proposal was not activated or benchmark-validated:

| Component | Purpose | Expected Gain |
|-----------|---------|---------------|
| **Semantic Understanding** | Extract canonical concepts from questions | +8-10% |
| **Cross-Source Validation** | Validate data across P6/SAP/TC | +12-15% |
| **Clarifying Questions** | Detect and resolve ambiguity | +5-8% |
| **Confidence Scoring** | Transparent data quality assessment | +4-6% |
| **Composite Metrics** | Multi-dimensional health analysis | +6-8% |
| **TOTAL UNVALIDATED PROJECTED GAIN** | **95% -> 99%+ target** | **+41-52%** |

---

## Archival Conditional Integration Procedure

The following instructions are preserved for historical reference. They must not be applied to the current production application without renewed testing, security review, benchmark validation, and explicit approval.

### 1. Installation (5 minutes)

All required files are in place:

```
backend/
  engine/
    ✅ accuracy_engines.py         (5 accuracy engines, 1000+ lines)
    ✅ orchestrator_v2_2.py        (Integration hub)
    ✅ (existing) data_schema.py   (Data understanding)
    ✅ (existing) visualizations.py (Chart generation)
    ✅ (existing) response_formatter.py (Response formatting)
    ✅ (existing) intent_v2.py     (Intent classification)
  routers/
    ✅ ai_v2_2.py                  (9 new endpoints)
    ✅ (existing) ai.py            (v2.1 - unchanged)
  
  main.py                            (Add v2.2 router)
```

### 2. Register Router (1 minute)

Edit `backend/main.py`:

```python
# Add import
from routers import ai_v2_2

# Add router (after existing routers)
app.include_router(ai_v2_2.router)

# Result: v2.2 endpoints available at /api/chat-v2.2, etc.
```

### 3. Test (2 minutes)

```python
# Start backend
cd backend && python run.py

# Test endpoint
curl -X POST http://localhost:8000/api/chat-v2.2 \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the project schedule status?",
    "projectId": "P001"
  }'

# Expected response: HIGH confidence answer with health score
```

---

## 📡 API Endpoints

### Chat Endpoints

#### POST `/api/chat-v2.2` - Ultra-Accurate Chat

**Request:**
```json
{
  "message": "What is our project status?",
  "projectId": "P001",
  "sessionId": "session-123",
  "history": [],
  "availableProjects": ["P001", "P002"]
}
```

**Response:**
```json
{
  "type": "response",
  "version": "2.2",
  "latency_ms": 245,
  "project_id": "P001",
  "answer": "Your project is AT RISK...",
  "health_status": "AT RISK",
  "confidence_level": "HIGH",
  "confidence": {
    "confidence_level": "HIGH",
    "confidence_score": 0.88,
    "disclaimer": "Data is current (updated 2 hours ago)..."
  },
  "composite_health": {
    "composite_health_score": 0.62,
    "health_status": "AT RISK",
    "primary_drivers": [
      {"metric": "schedule", "score": 0.45},
      {"metric": "cost", "score": 0.68}
    ],
    "recommendations": [
      "Add 2 weeks to schedule to de-risk",
      "Review procurement...",
      "Speed up critical path activities..."
    ]
  },
  "visualizations": [
    {"type": "activity_status_pie", "data": {...}}
  ]
}
```

**Status Codes:**
- `200` - Success
- `400` - Clarification needed (if `type: clarification_needed`)
- `500` - Error

---

#### POST `/api/chat-v2.2/stream` - Streaming Version

Same endpoint, but streams progress updates:

```
data: {"type": "progress", "step": "semantic_understanding", "label": "Analyzing question semantics..."}

data: {"type": "progress", "step": "data_validation", "label": "Validating data..."}

data: {"type": "response", "data": {...full response...}}
```

**Frontend Code:**
```javascript
const response = await fetch('http://localhost:8000/api/chat-v2.2/stream', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message, projectId})
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value);
  const events = text.split('\n').filter(l => l.startsWith('data: '));
  
  for (const event of events) {
    const data = JSON.parse(event.slice(6));
    console.log(data);
    // Update UI with progress or response
  }
}
```

---

### Validation Endpoints

#### GET `/api/validate/{projectId}` - Cross-Source Validation

Validates project data across P6, SAP, and TradeControl.

**Request:**
```
GET /api/validate/P001?projectId=P001
```

**Response:**
```json
{
  "projectId": "P001",
  "validation": {
    "overall_score": 0.87,
    "validated": true,
    "inconsistency_count": 1,
    "flags": [
      {
        "type": "schedule",
        "severity": "MEDIUM",
        "message": "SPI is 0.92 but estimated completion is 2 weeks late"
      }
    ],
    "scheduleValidation": {
      "spi": 0.92,
      "progress_alignment": true
    },
    "costValidation": {
      "cpi": 1.05,
      "spending_alignment": true
    },
    "progressValidation": {
      "activity_count": 45,
      "duration_alignment": true
    }
  }
}
```

---

### Confidence Endpoints

#### POST `/api/confidence` - Confidence Scoring

Get detailed confidence assessment.

**Request:**
```json
{
  "projectId": "P001"
}
```

**Response:**
```json
{
  "projectId": "P001",
  "confidence": {
    "confidence_level": "HIGH",
    "confidence_score": 0.88,
    "factors": {
      "data_freshness": {
        "age_hours": 2,
        "status": "FRESH",
        "score": 0.95
      },
      "data_completeness": {
        "required_fields_count": 20,
        "present_fields_count": 19,
        "score": 0.95
      },
      "data_consistency": {
        "inconsistencies": 1,
        "score": 0.80
      },
      "activity_data_quality": {
        "total_activities": 45,
        "incomplete": 3,
        "score": 0.93
      }
    },
    "disclaimer": "Analysis based on data updated 2 hours ago. One minor inconsistency detected in schedule vs cost metrics.",
    "suggestions": [
      "Update activity P-234 status",
      "Verify SAP cost data against actuals"
    ]
  }
}
```

---

### Clarification Endpoints

#### POST `/api/clarify` - Get Clarification Questions

Detect ambiguous queries and suggest clarifications.

**Request:**
```json
{
  "message": "Is the project OK?",
  "availableProjects": ["P001", "P002", "P003"]
}
```

**Response:**
```json
{
  "message": "Is the project OK?",
  "needsClarification": true,
  "clarifications": {
    "ambiguities_detected": [
      "Project not specified (3 available)",
      "Definition of 'OK' unclear (schedule, cost, progress?)"
    ],
    "questions": [
      "Which project do you want to analyze?",
      "Are you asking about schedule, cost, or overall status?"
    ],
    "suggested_response": "I found some ambiguity. Could you clarify:\n1. Which project? (P001, P002, or P003)\n2. What aspect? (Schedule, Cost, Progress, or Overall?)"
  }
}
```

---

#### POST `/api/semantic-analysis` - Semantic Understanding

Get semantic analysis of a question.

**Request:**
```json
{
  "message": "Show me CPI analysis for the project"
}
```

**Response:**
```json
{
  "message": "Show me CPI analysis for the project",
  "semantic": {
    "concepts": {
      "primary_concept": "cost_performance",
      "related_concepts": ["cost", "earned_value", "financial_health"],
      "confidence": 0.94
    },
    "hidden_needs": [
      "wants_visual_representation",
      "wants_trend_analysis",
      "wants_comparison"
    ],
    "rephrased": "Analyze cost performance index (CPI) trends and current status"
  }
}
```

---

### Health Score Endpoints

#### POST `/api/health-score` - Composite Health Score

Get comprehensive project health assessment.

**Request:**
```json
{
  "projectId": "P001"
}
```

**Response:**
```json
{
  "projectId": "P001",
  "health": {
    "composite_health_score": 0.62,
    "health_status": "AT RISK",
    "component_scores": {
      "schedule": 0.45,
      "cost": 0.68,
      "progress": 0.75,
      "critical_path": 0.55,
      "activity_health": 0.70
    },
    "health_trend": "DEGRADING",
    "primary_drivers": [
      {
        "rank": 1,
        "metric": "schedule",
        "score": 0.45,
        "contribution": "PRIMARY",
        "reason": "2 weeks behind schedule"
      },
      {
        "rank": 2,
        "metric": "critical_path",
        "score": 0.55,
        "contribution": "SIGNIFICANT",
        "reason": "Critical path has 3 at-risk activities"
      }
    ],
    "recommendations": [
      "Add 2 weeks to schedule buffer",
      "Accelerate M-102 (critical path)",
      "Resolve 3 resource conflicts",
      "Review procurement delay for component X"
    ]
  }
}
```

---

### Feedback Endpoints

#### POST `/api/feedback` - Submit Feedback

Provide feedback on chatbot responses (improves accuracy over time).

**Request:**
```json
{
  "messageId": 12345,
  "feedbackType": "accuracy",
  "correctionText": "Health score was actually CRITICAL, not AT RISK",
  "projectId": "P001",
  "confidenceCorrect": false,
  "healthScoreCorrect": false
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Feedback received and stored"
}
```

**Feedback Types:**
- `accuracy` - Response accuracy correction
- `confidence` - Confidence level incorrect
- `health` - Health score incorrect
- `helpful` - General helpfulness
- `other` - Other feedback

---

## 🎯 Usage Patterns

### Pattern 1: Simple Status Check

```javascript
const response = await fetch('/api/chat-v2.2', {
  method: 'POST',
  body: JSON.stringify({
    message: "What's the project status?",
    projectId: "P001"
  })
});
const data = await response.json();
console.log(data.answer);           // Full response with insights
console.log(data.health_status);    // "EXCELLENT", "HEALTHY", "AT RISK", etc.
console.log(data.confidence_level); // "HIGH", "MEDIUM", "LOW"
```

### Pattern 2: Ambiguous Query with Clarification

```javascript
const response = await fetch('/api/chat-v2.2', {
  method: 'POST',
  body: JSON.stringify({
    message: "Is the project OK?"
  })
});
const data = await response.json();

if (data.type === 'clarification') {
  // Show clarification questions to user
  console.log(data.questions);
  // User selects answer, resubmit with specific info
}
```

### Pattern 3: Validation + Health Check

```javascript
// Check data consistency
const validation = await fetch('/api/validate/P001').then(r => r.json());
if (validation.validation.inconsistency_count > 0) {
  console.warn('Data issues:', validation.validation.flags);
}

// Get health score
const health = await fetch('/api/health-score', {
  method: 'POST',
  body: JSON.stringify({projectId: "P001"})
}).then(r => r.json());

console.log(health.health.recommendations); // Actionable advice
```

### Pattern 4: Streaming Response with Progress

```javascript
const eventSource = new EventSource('/api/chat-v2.2/stream', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message, projectId})
});

eventSource.onmessage = (event) => {
  const {type, step, data} = JSON.parse(event.data);
  if (type === 'progress') {
    console.log(`Progress: ${step}`);
    ui.showProgress(step);
  } else if (type === 'response') {
    eventSource.close();
    ui.showResponse(data);
  }
};
```

---

## Archived Migration Proposal

These options describe an unexecuted historical rollout proposal, not a current recommendation.

### Option 1: Historical Gradual Rollout Proposal

**Phase 1: Dual Operation (Week 1)**
- Preserve the then-active endpoints
- Conditionally activate v2.2 endpoints in an isolated environment
- Route new chat through v2.2
- Keep dashboards using v2.1 temporarily

**Phase 2: Monitor & Validate (Week 2)**
- Monitor v2.2 accuracy metrics
- Collect user feedback via `/api/feedback`
- Validate confidence scores vs reality
- Check performance metrics

**Phase 3: Switch to v2.2 (Week 3)**
- Migrate all chat to v2.2
- Update dashboards to use new health scores
- Monitor for any issues
- Keep rollback option available

**Phase 4: Retire v2.1 (Week 4+)**
- Remove v2.1 endpoints (optional)
- Archive old models
- Keep v2.1 code for reference

### Option 2: Historical Big Bang Proposal (Not Recommended)

- Conditionally activate v2.2 after validation and approval
- Immediately route all traffic through new endpoints
- Monitor closely for issues
- Rollback available if needed

### Option 3: A/B Testing

- Route 50% of traffic to v2.2
- Route 50% to v2.1
- Compare accuracy metrics
- Gradually increase v2.2 percentage
- Abandon v2.1 once v2.2 stabilizes

---

## 📊 Monitoring

### Key Metrics to Track

1. **Accuracy Metrics**
   - Intent classification accuracy
   - Health score accuracy vs reality
   - Confidence score calibration
   - False positive rate (wrong clarifications)

2. **Performance Metrics**
   - Response latency (target: <500ms)
   - Validation latency
   - Confidence scoring latency
   - Overall pipeline latency

3. **Quality Metrics**
   - Feedback submission rate
   - Correction rate (how often users correct responses)
   - Confidence level distribution
   - Health status distribution

4. **Usage Metrics**
   - Queries needing clarification
   - Queries needing validation
   - Average confidence per query type
   - Feature usage (health scores, confidence, validation)

### Dashboard Query

```python
# Track metrics over time
SELECT 
  DATE(created_at) as date,
  COUNT(*) as total_queries,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN feedback = 'correct' THEN 1 ELSE 0 END) as correct_responses,
  SUM(CASE WHEN needs_clarification THEN 1 ELSE 0 END) as clarifications
FROM chatbot_queries
WHERE created_at > NOW() - INTERVAL 7 DAYS
GROUP BY DATE(created_at)
```

---

## 🛠️ Troubleshooting

### Issue: "Module not found" error

**Solution:**
```bash
# Ensure files exist
ls -la backend/engine/accuracy_engines.py
ls -la backend/engine/orchestrator_v2_2.py
ls -la backend/routers/ai_v2_2.py

# Check imports in main.py
grep "from routers import" backend/main.py
```

### Issue: Slow responses

**Solution:**
```python
# Add timing
import time
start = time.time()
response = orchestrator.process_message_v2(...)
latency = (time.time() - start) * 1000
print(f"Latency: {latency}ms")

# If >500ms, check:
# 1. Database queries - add indexes
# 2. Validation - cache validation results
# 3. Confidence scoring - parallel scoring
```

### Issue: Low confidence scores

**Solution:**
```python
# Check data freshness
confidence = orchestrator.confidence_scorer.score_response_confidence(project_id)
print(confidence['factors']['data_freshness'])

# If old, trigger data refresh:
# - Update P6 sync
# - Update SAP sync
# - Update TC sync
```

### Issue: Frequent clarifications

**Solution:**
```python
# Check clarifier sensitivity
clarifications = orchestrator.clarifier.generate_clarification_questions(...)
# Adjust ambiguity threshold if too sensitive
# Review ambiguity patterns in logs
```

---

## 🚨 Fallback / Rollback

### If v2.2 has issues:

```python
# In main.py
USE_V2_2 = True  # Set to False to disable v2.2

# Or route to v2.1
if USE_V2_2:
  orchestrator = ChatbotV22Orchestrator(db)
else:
  orchestrator = ChatOrchestrator(db)  # v2.1 fallback
```

### Database rollback (if needed):

```sql
-- Keep v2.2 metadata separate
ALTER TABLE chatbot_responses ADD COLUMN version VARCHAR(10);
UPDATE chatbot_responses SET version='2.1';

-- v2.2 queries
INSERT INTO chatbot_responses (response, version, confidence, ...) 
VALUES (..., '2.2', ...);

-- Rollback queries
SELECT * FROM where version='2.1';
```

---

## 📈 Unvalidated Projected Results

### Before v2.2 (v2.1):
- Overall Accuracy: ~85% unvalidated baseline estimate
- Intent Classification: 90-95% unvalidated estimate
- False Positives: ~8-10%
- Response Time: 200-300ms
- User Satisfaction: 3.2/5

### After v2.2:
- Overall Accuracy: 95-99%+ unvalidated target
- Intent Classification: 97-98%
- False Positives: <2%
- Response Time: 300-500ms
- User Satisfaction: 4.5+/5

### Per-Module Gains:
1. Semantic Understanding: Foundation for all others
2. Clarifying Questions: Unvalidated target of reducing misunderstandings by 95%+
3. Cross-Source Validation: Catches ~12-15% more issues
4. Confidence Scoring: Builds trust (transparent failures, not false successes)
5. Composite Metrics: Multi-dimensional analysis prevents tunnel vision

---

## Archived Conditional Next Steps

1. **Validate in Isolated Infrastructure**
   - Add v2.2 router to main.py
   - Start backend
   - Verify endpoints respond

2. **Frontend Integration**
   - Update chat component to use `/api/chat-v2.2`
   - Add confidence level display
   - Add health score visualization
   - Handle clarification questions UI

3. **Testing**
   - Unit tests for each engine
   - Integration tests for full pipeline
   - Performance tests (latency, throughput)
   - User acceptance testing

4. **Monitoring**
   - Set up dashboards for key metrics
   - Create alerts for issues
   - Track accuracy improvements
   - Collect user feedback

5. **Documentation**
   - Write deployment guide
   - Document API in Swagger
   - Create user guides
   - Record video tutorials

---

## 📞 Support

**Questions?**
- Check logs: `tail -f backend.log | grep v2.2`
- Test endpoints: Use the curl examples above
- Check configuration: `CHATBOT_VERSION=2.2` environment variable
- Review architecture: See `ACCURACY_IMPROVEMENTS.md`

**Performance Issues?**
- Enable debug logging: `LOG_LEVEL=DEBUG`
- Profile with: `python -m cProfile -s cumulative backend/main.py`
- Check database indexes
- Monitor API latencies

**Accuracy Issues?**
- Review feedback: SELECT * FROM feedback WHERE accuracy = FALSE
- Check validation flags
- Examine confidence scores
- Submit feature requests

---

**Inactive historical prototype: do not deploy to production without current validation and explicit approval.**
