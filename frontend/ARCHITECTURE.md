# Frontend Architecture & Development Rules

This document outlines the strict architecture and development rules for the Akasha Platform frontend, as defined by the user.

## Development Rules

1. Do not create large monolithic pages.
2. Do not create components exceeding 500 lines.
3. Do not create pages exceeding 1000 lines.
4. Always reuse existing components before creating new ones.
5. Separate UI, business logic, API calls, state management, and types.
6. Build every module as an independent feature that can scale later.
7. Use TypeScript strictly with proper interfaces and types.
8. Follow feature-based architecture.

## Project Structure

```
src/
├── app/
├── components/
│   ├── ui/
│   ├── shared/
│   ├── layouts/
│   ├── charts/
│   └── forms/
│
├── features/
│   ├── dashboard/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── pages/
│   │
│   ├── executive-briefing/
│   ├── chatbot/
│   ├── analytics/
│   ├── reports/
│   ├── projects/
│   ├── approvals/
│   └── settings/
│
├── services/
├── hooks/
├── store/
├── lib/
├── utils/
├── constants/
├── types/
└── assets/
```

## Component Strategy

Create reusable components only once.

Shared Components:
* DataTable
* KPI Card
* Metric Card
* Status Badge
* Filter Bar
* Search Input
* Chart Wrapper
* Drawer
* Modal
* Tabs
* Empty State
* Error State
* Loading State
* AI Insight Card
* Executive Summary Card

## Dashboard Structure

```
Dashboard
├── Header
├── Global Filters
├── KPI Section
├── Executive Briefing
├── AI Recommendations
├── Trend Analytics
├── Alerts & Risks
├── Recent Activities
└── Quick Actions
```
Each section should be a separate component.

## Executive Briefing

```
ExecutiveBriefing
├── Summary Card
├── Risk Card
├── Opportunity Card
├── Recommendation Card
├── Action Items
└── Drill-down Drawer
```
Do not place everything on one screen.
Open details in drawers or side panels.

## AI Chat Structure

```
AIChat
├── Chat Layout
├── Message List
├── Message Bubble
├── Suggested Prompts
├── Source References
├── Agent Selector
├── Conversation History
└── AI Insights Panel
```

## Analytics Structure

```
Analytics
├── Filters
├── KPI Overview
├── Trend Charts
├── Comparison Charts
├── Breakdown Tables
└── Export Actions
```

## Data Flow

`UI Components -> Feature Hooks -> Services -> API Layer -> Backend`

**Never call APIs directly inside UI components.**

## State Management

Global State:
* User
* Authentication
* Theme
* Notifications
* Global Filters

Feature State:
* Dashboard Data
* Reports
* Chat Sessions
* Analytics Filters

## Performance Rules

* Lazy load pages.
* Lazy load charts.
* Use pagination.
* Use virtualization for large tables.
* Cache API responses.
* Memoize expensive calculations.
* Avoid unnecessary re-renders.

## UI Quality Standards

Design should feel similar to:
* ChatGPT
* Linear
* Notion
* Stripe Dashboard
* Vercel
* Retool

Requirements:
* Clean spacing
* Premium cards
* Consistent typography
* Professional colors
* Responsive layouts
* Smooth animations
* Modern interactions

## Final Rule

Whenever implementing a feature:
1. Check for reusable components first.
2. Create feature-specific components only when necessary.
3. Keep files small and readable.
4. Split large screens into sections.
5. Maintain scalability and enterprise-grade code quality.
6. Prioritize maintainability over quick implementation.
