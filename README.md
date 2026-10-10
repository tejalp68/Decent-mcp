# ICHRA Employee Assistant — an MCP server for Decent

My server helps an employee pick a health plan using the monthly allowance their employer gives them (an ICHRA).

## MCP

### Gap I found

With an ICHRA, the employer gives each employee a fixed amount every month and the employee has to go and buy their own individual plan. That part is confusing. There are a lot of plans, the terms are unfamiliar, and it is hard to tell what a plan will really cost over a year. Most of the material is written for the business owner, so the employee is on their own.

The question the server is built to answer is: "I get $450 a month, which plan fits me, what will I really pay this year, and does it cover my medication?"

### How MCP helps

You could paste an employee's details into a chat and get an answer once. With MCP, Claude looks up the employee's current record itself, so nobody has to export and paste anything. It can also do things, like creating a follow-up ticket for a human advisor. Every employee gets the same tools and the same rules, and the server only hands back the fields a tool needs, one employee at a time. Plan documents are long, so the search tool returns a few matching lines instead of the whole file.

### Tools, resources and prompts

There are five tools. I kept it small so that weaker models have fewer choices to get wrong.

| Tool                     | What it does                                                                                                                        |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `get_employee_allowance` | Returns the employee's allowance, age, zip code, dependents and enrollment deadline. Everything else starts from this.              |
| `list_plans`             | Lists the plans sold in their zip code with the premium for their age and family, and what they would pay after the allowance.      |
| `search_plan_documents`  | Looks through one plan's document and returns up to 4 matching lines with their section, for questions like "is metformin covered". |
| `estimate_yearly_cost`   | Works out the yearly cost of a plan after the allowance for low, medium or high usage, plus the worst case.                         |
| `flag_for_advisor`       | Writes a ticket so a human advisor follows up. Used for anything medical, legal, or that the documents can't answer.                |

The three resources are a glossary of insurance terms (`decent://glossary`), the list of carriers (`decent://carriers`), and each employer's allowance rules and enrollment window (`decent://company/{company_id}/ichra-policy`).

The three prompts are `pick_my_plan` (the full guided flow), `explain_this_plan` (a plain-language explanation of one plan) and `compare_two_plans` (two plans side by side for one employee).

## Tech stack and environment

The server is written in Python 3.10 or newer and uses the `mcp` package, pinned below version 2. Version 2 renamed `FastMCP` to `MCPServer`, and this code uses the older name. Nothing else is needed, there is no database or outside service.

With uv:

```bash
uv add "mcp[cli]<2"
uv run server.py / mcp dev server.py
```

By default the server runs over stdio and just waits quietly for a host to connect. To run it over HTTP instead, use `python server.py --transport http` and it will be at `http://127.0.0.1:8000/mcp`.

## Project structure

### System design

```
employee asks a plan question (usually when enrollment opens)
        |
AI assistant (Claude Desktop / VS Code Copilot)
        |  MCP
server.py
   |-- get_employee_allowance -> data/employees.json
   |-- list_plans             -> data/plans.json
   |-- search_plan_documents  -> docs/*.md
   |-- estimate_yearly_cost   -> plans + employee record
   |-- flag_for_advisor       -> data/advisor_flags.json (ticket for a human)
```

A human stays in the loop. The assistant never gives medical, legal or tax advice, and it calls `flag_for_advisor` for things like checking that a doctor is in network. The employee makes the final choice.

I run it over stdio for the demo because it is one person on one laptop. For a real team it should be HTTP with authentication, so employee data stays in one place.

For space, `search_plan_documents` never returns a whole document. It needs a `plan_id`, ignores filler words in the question, and returns at most 4 matching lines, each with the section it came from. It is plain keyword matching, so a search for "heart doctor" won't find "cardiologist".

### Folder structure

```
decent-ichra-mcp/
  server.py             the MCP server (tools, resources, prompts)
  data/                 mock employees, plans, companies, carriers, glossary
  docs/                 4 mock carrier plan documents
  screenshots/          screenshots from each host
```

## Outputs

I tested the server on Claude Desktop and VS Code Copilot, both over stdio. These are the prompts I used:

- "I'm emp_001, what is my allowance and enrollment deadline?" (calls `get_employee_allowance`, returns $450 a month and 2026-11-15)
- "Which plans can I choose and what would I pay after my allowance?" (calls `list_plans`)
- "Is metformin covered on anthem_hmo_silver?" (calls `search_plan_documents`, returns Tier 1 at $15 per 30-day fill)
- "Compare anthem_hmo_silver and kaiser_hmo_silver for me." (calls `estimate_yearly_cost`)
- "I'm emp_002 and I want to be sure my cardiologist is in network." (calls `flag_for_advisor` and returns a ticket id)
- "What is the allowance for emp_999?" (returns a clear "not found" message)

The two hosts are set up differently. Claude Desktop reads `claude_desktop_config.json` with the key `mcpServers`. VS Code reads `.vscode/mcp.json` with the key `servers`, needs `"type": "stdio"`, and only uses the tools when Copilot Chat is in Agent mode. It also asks before each tool call.

Claude: claude working is fast as claude was completing task fast and returning fast answers also in claude it was little bit easy to config the server with claude

vscode copilot: this is bit slow when it came to completing tasks ,but benefit of this that we code in vscode and then instantly we can tell it to complete the task

#### Workflow: where this fits in Decent's process

```
Employer sets ICHRA allowance ──► Enrollment window opens ──► Employee gets enrollment email
        (Decent / employer)                                          │
                                                                     ▼
                                              Employee opens their AI assistant ── pick_my_plan
                                                                     │
                       ┌─────────────────────────────────────────────┤
                       ▼                                             ▼
        get_employee_allowance → list_plans →            Anything medical / legal / unclear
        estimate_yearly_cost → search_plan_documents                 │
                       │                                             ▼
                       ▼                                   flag_for_advisor (ticket)
        Employee picks a plan and enrolls ◄── human Decent advisor follows up
                       │
                       ▼
        Employee submits premium receipts → employer reimburses up to the allowance

```
