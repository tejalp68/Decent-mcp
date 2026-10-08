"""Connect to the server over real stdio (like Claude Desktop does) and exercise tools/resources/prompts."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print("TOOLS:", [t.name for t in tools])
            print("RESOURCES:", [str(x.uri) for x in (await s.list_resources()).resources])
            print("TEMPLATES:", [x.uriTemplate for x in (await s.list_resource_templates()).resourceTemplates])
            print("PROMPTS:", [p.name for p in (await s.list_prompts()).prompts])

            res = await s.call_tool("get_employee_allowance", {"employee_id": "emp_001"})
            print("\nget_employee_allowance ->", res.content[0].text)

            res = await s.call_tool("search_plan_documents",
                                    {"query": "do I need a referral to see a specialist", "plan_id": "anthem_hmo_silver"})
            d = json.loads(res.content[0].text)
            print("\nsearch_plan_documents -> top section:", d["passages"][0]["section"],
                  "| tokens returned:", d["tokens_returned"], "| full doc:", d["tokens_in_full_document"])

            bad = await s.call_tool("get_employee_allowance", {"employee_id": "zzz"})
            print("\nerror path -> isError =", bad.isError, "|", bad.content[0].text[:110])

            doc = await s.read_resource("decent://company/acme_dental/ichra-policy")
            print("\nresource policy ->", json.loads(doc.contents[0].text)["enrollment_window"])

            pr = await s.get_prompt("pick_my_plan", {"employee_id": "emp_001"})
            print("prompt pick_my_plan -> first line:", pr.messages[0].content.text.splitlines()[0])


asyncio.run(main())
