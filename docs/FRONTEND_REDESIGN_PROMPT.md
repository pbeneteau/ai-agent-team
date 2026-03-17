# Frontend Redesign Planning Prompt

Use the prompt below to ask an LLM for a serious redesign plan to transform the current frontend into a more professional, clearer, more powerful, Linear-like product experience.

This prompt is designed to produce a planning document, not code.

---

## Copy-Paste Prompt

```md
You are a principal product designer, staff frontend architect, and expert in designing premium SaaS interfaces.

Your mission is to produce a serious redesign plan for an existing frontend that currently feels too dense, too text-heavy, too fragmented, and not productized enough.

The goal is to transform it into a more professional, more focused, more powerful dashboard-style product experience inspired by the quality bar of tools like Linear, while still fitting this product’s own workflows and complexity.

This is NOT a request for code.
This is NOT a request for a visual moodboard.
This is a request for a concrete redesign plan that can be implemented by engineers.

## Product Context

The product is an AI agent orchestration platform with concepts such as:
- chat / assistant interaction
- project context / brief / shared documents
- teams and agents
- tasks and task execution results
- usage / AI observability
- external connections

The current frontend problems are:
- too much text
- too many overloaded pages
- poor information hierarchy
- weak navigation clarity
- too many mixed concerns on the same page
- not enough page splitting
- not enough sense of operational power
- too much “tooling/debug/admin UI” feeling
- not enough premium product feel
- important actions and signals are buried in noise

I want the redesigned frontend to feel:
- professional
- clean
- sharp
- high-signal
- confident
- operational
- fast to parse
- premium
- more Linear-like in discipline and clarity

Important nuance:
- Do NOT copy Linear blindly.
- Use Linear as a quality bar for clarity, density discipline, layout confidence, and interaction polish.
- The result must fit this product’s specific workflows, which are broader and more AI-heavy than a ticketing tool.

## Technical Direction

The redesign should assume a React / Next.js frontend and a UI architecture built around Radix UI primitives.

You may recommend:
- Radix primitives directly
- or a structured design system built on top of Radix

But the plan must explicitly think in terms of:
- reusable layout primitives
- reusable navigation patterns
- consistent shells
- dialog/drawer/popover strategy
- tabs / segmented navigation
- density system
- typography hierarchy
- cards, lists, panels, and inspector patterns
- standardized empty / loading / error states

## What you need to do

Create a redesign plan that covers:

### 1. Product-level UX diagnosis
- What is fundamentally wrong with the current frontend structure?
- Why does it not feel premium enough?
- Why does it not feel powerful enough?
- Why is it cognitively heavy?

### 2. New product architecture
- Propose a cleaner top-level information architecture.
- Define the ideal primary navigation.
- Define what should become full pages.
- Define what should remain a drawer, modal, popover, tab, side panel, or inline section.
- Clarify where the true centers of gravity of the product should be.

### 3. Dashboard strategy
- Propose what the main dashboard/home should become.
- It should feel like an operational control center, not a wall of text or metrics.
- It should surface priorities, blockers, next actions, and system state clearly.
- Explain what should be visible above the fold.

### 4. Page splitting strategy
- Identify which current pages are overloaded and should be split.
- Explain exactly how to split them.
- If some pages should become multi-tab workspaces, say so.
- If some content should be moved into a dedicated detail page instead of a modal/drawer, say so.

### 5. Visual hierarchy and interaction model
- Define the design principles that should guide the new UI.
- Explain how to reduce noise.
- Explain how to reduce text density.
- Explain how to make the product feel faster and more confident.
- Explain how to communicate “power” through layout and hierarchy rather than through verbose explanations.

### 6. Radix-oriented component system
- Propose the core UI primitives and page-level patterns to standardize.
- Examples: app shell, top bar, side navigation, section header, command bar, inspector panel, settings form, data list, activity feed, result summary, status chips, empty states, tabs, modal, drawer.
- Indicate which Radix primitives are especially relevant.
- Recommend where to use dialogs vs drawers vs inline editing vs dedicated pages.

### 7. Migration strategy
- Propose a phased implementation plan.
- Prioritize the highest-leverage structural changes first.
- Separate:
  - quick wins
  - medium redesigns
  - major structural refactors
- The plan should be realistic for an engineering team to implement incrementally.

### 8. Guardrails
- Explicitly say what NOT to do.
- Prevent the redesign from becoming:
  - overly decorative
  - too minimal to support a complex product
  - too inspired by Linear without adapting to product needs
  - another heavy admin panel

## Constraints

- Be concrete, not vague.
- Focus on frontend structure, navigation, UX, hierarchy, and interaction design.
- Do not spend time on backend architecture.
- Do not suggest generic advice like “improve spacing” or “make it cleaner” without structural recommendations.
- Prioritize information architecture and workflow clarity over cosmetic polish.
- Optimize for a serious founder/operator/power-user audience.
- Assume desktop-first, but consider narrow laptop widths.
- Treat this as a product redesign plan for a real SaaS tool, not a student exercise.

## Output format

Return your answer in exactly this structure:

# Executive Direction
Give a direct summary of the redesign direction and the target product feel.

# Core Problems to Solve
List the fundamental frontend issues that must be fixed first.

# Target Product Model
Explain the new mental model and top-level structure of the product.

# Proposed Navigation Architecture
Define:
- primary nav
- secondary nav
- page grouping
- major workspace boundaries

# Dashboard Redesign
Explain exactly how the dashboard/home should work.

# Page-by-Page Restructuring Plan
For each major page/surface:
- current problem
- redesign direction
- keep / remove / split / merge
- target interaction model

# Radix-Based UI System Plan
Define the core primitives, layout patterns, and interaction patterns to standardize.

# Phased Implementation Roadmap
Split into:
- Phase 1: quick wins
- Phase 2: structural redesign
- Phase 3: refinement and systemization

# Risks and Anti-Patterns
Explain what mistakes to avoid during the redesign.

# Final Recommended Priorities
Give the top 10 actions in recommended execution order.

## Style requirements

- Be opinionated.
- Be practical.
- Be specific.
- Think like a top product design lead and frontend architecture lead working together.
- Favor clarity, leverage, and product power.
- Avoid generic “design thinking” fluff.
- The plan should feel implementable.
```

---

## Recommended Inputs To Provide With The Prompt

To get the best result, provide:
- screenshots of the main pages
- a route map or sitemap
- short explanation of key workflows
- current navigation structure
- optionally the main page components and shared layout components

Best pages to include:
- `Home / Dashboard`
- `Chat / Assistant`
- `Project Context`
- `Teams & Agents`
- `Tasks`
- `Task Detail`
- `Usage / Observability`
- `Connections`

## Optional Stronger Variant

Add this sentence before sending the prompt if you want a more aggressive answer:

```md
Do not optimize for preserving the current structure. Optimize for the strongest possible product experience, even if it requires major page re-architecture.
```

## Expected Outcome

This prompt should produce:
- a serious redesign plan
- a clearer product architecture
- a more disciplined dashboard strategy
- a Radix-oriented component/system plan
- an implementation roadmap for turning the current frontend into a more premium, powerful, product-grade experience
