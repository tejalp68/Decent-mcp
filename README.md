# ICHRA Employee Assistant: an MCP server for Decent

> All data in this repo is **mock data** created for a assignment. Nothing here is a real quote, plan or medical/insurance advice.

## 1. Company

**Decent** ([decent.com](https://www.decent.com/)) is an AI-native health insurance brokerage for small businesses. It prices every way to cover a team (standard fully insured plans, and ICHRA, where the company gives each employee a monthly amount to buy their own plan), helps the owner pick one, and reviews claims data year-round instead of only at renewal.
**Users:** small-business owners and the employees who end up with the plan.

## 2. The problem this server solves

With an **ICHRA**, the owner's job gets easier but the _employee's_ job gets harder: they receive, say, $450/month and must shop for their own plan among dozens of options, most of which they can't compare. As far as I could tell from the public site, Decent's pitch speaks mainly to the business owner, so the employee side step is the gap this server targets.

**What it does:** an employee asks their AI assistant _"I get $450 a month, what should I pick?"_ and the assistant can look up their real allowance, list the plans sold in their zip code, estimate their yearly cost per plan, answer specific questions from the carrier documents ("is metformin covered?", "do I need a referral?"), and hand off to a human Decent advisor when it shouldn't guess.

### Why MCP and not just paste the data into Claude?

For a one-off question, pasting works. MCP earns its place here because:

| Need                                            | Pasting                                                        | This server                                                |
| ----------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------- |
| Employee's real, current allowance and deadline | Employee types it from memory                                  | Fetched live by `get_employee_allowance`                   |
| Plan documents                                  | A full evidence-of-coverage packet floods the context (see §7) | RAG tool returns only the 3 relevant passages              |
| Taking an action                                | Impossible                                                     | `flag_for_advisor` creates a ticket for a human            |
| Same behaviour for every employee               | Everyone pastes something different                            | One server, same tools and rules for all                   |
| Access control                                  | Whole spreadsheets pasted into chats                           | Server decides what each call can return (see Limitations) |

## 3. Tools, resources and prompts (and why)

### Tools (5): things the model _does_

| Tool                     | What it does                                                                            | Why it exists                                                 |
| ------------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `get_employee_allowance` | Allowance, age, zip, dependents, enrollment deadline for one employee                   | Live data every later step depends on                         |
| `list_plans`             | Plans sold in a zip code, with the premium for that age/household                       | Core "what are my options" step                               |
| `search_plan_documents`  | **RAG** over carrier documents; returns top-k passages                                  | Specific questions without dumping whole documents            |
| `estimate_yearly_cost`   | Premium after allowance + expected out-of-pocket + worst case, at low/medium/high usage | Turns plan features into one comparable number                |
| `flag_for_advisor`       | Writes a ticket for a human advisor                                                     | Human-in-the-loop for anything medical, legal, tax or unclear |

### Resources (3): read-only context the model can _read_

- `decent://glossary`: plain-language definitions (deductible, HMO, ICHRA, ...).
- `decent://carriers`: carriers, plan types and states.
- `decent://company/{company_id}/ichra-policy`: the employer's allowance rules and enrollment window (a resource _template_).

### Prompts (3): reusable guided workflows

- `pick_my_plan(employee_id)`: the full guided flow (allowance → one question → plans → estimates → recommendation, with a handoff rule).
- `explain_this_plan(plan_id)`: jargon-free explanation under 150 words.
- `compare_two_plans(plan_a, plan_b, employee_id)`: side-by-side at low/medium/high usage.

**Kept deliberately small:** five tools, each doing one job, rather than ten half-working ones.

## 4. How to run

```bash
git clone <your-repo-url> && cd decent-ichra-mcp
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt


python server.py                        # stdio (what Claude Desktop / Cursor launch)
python server.py --transport http       # HTTP at http://127.0.0.1:8000/mcp
```
