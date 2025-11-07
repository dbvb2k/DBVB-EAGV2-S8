from typing import List, Optional
from modules.perception import PerceptionResult
from modules.memory import MemoryItem
from modules.model_manager import ModelManager
from dotenv import load_dotenv
from google import genai
import os
import asyncio

# Import config for receiver email
try:
    import config
    RECEIVER_EMAIL = getattr(config, 'RECEIVER_EMAIL', 'dbvb2k.aws@gmail.com')
except ImportError:
    RECEIVER_EMAIL = 'dbvb2k.aws@gmail.com'

# Optional: import logger if available
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

model = ModelManager()


async def generate_plan(
    perception: PerceptionResult,
    memory_items: List[MemoryItem],
    tool_descriptions: Optional[str] = None,
    step_num: int = 1,
    max_steps: int = 3
) -> str:
    """Generates the next step plan for the agent: either tool usage or final answer."""

    memory_texts = "\n".join(f"- {m.text}" for m in memory_items) or "None"
    tool_context = f"\nYou have access to the following tools:\n{tool_descriptions}" if tool_descriptions else ""

    prompt = f"""
You are a reasoning-driven AI agent with access to tools and memory.
Your job is to solve the user's request step-by-step by reasoning through the problem, selecting a tool if needed, and continuing until the FINAL_ANSWER is produced.

Respond in **exactly one line** using one of the following formats:

- FUNCTION_CALL: tool_name|param1=value1|param2=value2
- FINAL_ANSWER: [your final result] *(Not description, but actual final answer)

🧠 Context:
- Step: {step_num} of {max_steps}
- Memory: 
{memory_texts}
{tool_context}

🎯 Input Summary:
- User input: "{perception.user_input}"
- Intent: {perception.intent}
- Entities: {', '.join(perception.entities)}
- Tool hint: {perception.tool_hint or 'None'}

✅ Examples:
- FUNCTION_CALL: add|a=5|b=3
- FUNCTION_CALL: strings_to_chars_to_int|input.string=INDIA
- FUNCTION_CALL: int_list_to_exponential_sum|input.int_list=[73,78,68,73,65]
- FINAL_ANSWER: [42] → Always mention final answer to the query, not that some other description.

✅ Examples:

**Example 1: Simple Winner Query**
- User asks: "Find the winner in Women's Cricket World Cup in 2025"
  - Step 1: FUNCTION_CALL: search|query="winner of Women's Cricket World Cup 2025"
  - [receives search results showing India won]
  - Step 2: FUNCTION_CALL: fetch_content|url="<most relevant URL from search results>"
  - [receives detailed information about the match, score, players, etc.]
  - Step 3: FUNCTION_CALL: create_google_sheet|title="2025 Women's Cricket World Cup Winner"|column_headers=["Event", "Year", "Winner", "Runner-up", "Score", "Details"]|data=[["Women's Cricket World Cup", "2025", "India", "South Africa", "Won by 52 runs", "India won their maiden title, Deepti Sharma was Player of the Tournament"]]
  - [receives sheet_url from create_google_sheet response]
  - Step 4: FUNCTION_CALL: send_sheet_link|to="{RECEIVER_EMAIL}"|sheet_url="<sheet_url from step 3>"|sheet_title="2025 Women's Cricket World Cup Winner"
  - FINAL_ANSWER: [India won the Women's Cricket World Cup in 2025, defeating South Africa by 52 runs in the final. A Google Sheet with complete details has been created and sent to your email.]

**Example 2: Standings Query**
- User asks: "Find the Current Point Standings of F1 Racers"
  - Step 1: FUNCTION_CALL: search|query="F1 current point standings"
  - [receives search results - pick the most relevant URL]
  - Step 2: FUNCTION_CALL: fetch_content|url="https://www.espn.com/f1/standings" (or similar URL from search results)
  - [receives actual standings data with driver names and points]
  - Step 3: FUNCTION_CALL: create_google_sheet|title="F1 Current Point Standings"|column_headers=["Position", "Driver", "Points"]|data=[["1", "Max Verstappen", "357"], ["2", "Lewis Hamilton", "356"], ["3", "Charles Leclerc", "321"]]
  - [receives sheet_url from create_google_sheet response]
  - Step 4: FUNCTION_CALL: send_sheet_link|to="{RECEIVER_EMAIL}"|sheet_url="<sheet_url from step 3>"|sheet_title="F1 Current Point Standings"
  - FINAL_ANSWER: [F1 Current Point Standings: 1st place Max Verstappen with 357 points, 2nd place Lewis Hamilton with 356 points, 3rd place Charles Leclerc with 321 points. A Google Sheet with the complete standings has been created and sent to your email.]

**Example 3: Relationship/Descriptive Query (no sheet needed)**
- User asks: "What's the relationship between Cricket and Sachin Tendulkar"
  - FUNCTION_CALL: search_documents|query="relationship between Cricket and Sachin Tendulkar"
  - [receives a detailed document]
  - FINAL_ANSWER: [Sachin Tendulkar is widely regarded as the "God of Cricket" due to his exceptional skills, longevity, and impact on the sport in India. He is the leading run-scorer in both Test and ODI cricket, and the first to score 100 centuries in international cricket. His influence extends beyond his statistics, as he is seen as a symbol of passion, perseverance, and a national icon.]

---

📏 IMPORTANT Rules:

- 🚫 Do NOT invent tools. Use only the tools listed above. Tool description has useage pattern, only use that.
- 📄 If the question may relate to public/factual knowledge (like companies, people, places), use the `search` or `search_documents` tool to look for the answer.
- 🧮 If the question is mathematical, use the appropriate math tool.
- 📊 **MANDATORY: For ALL informational/factual queries (sports, history, statistics, winners, standings, rankings, etc.):**
  **YOU MUST ALWAYS:**
  1. Search for the information using `search` or `search_documents`
  2. If search returns URLs, use `fetch_content` to get detailed data from the most relevant URL
  3. Create a Google Sheet with the information using `create_google_sheet`:
     - For winners/titles: Create a sheet with columns like ["Event", "Year", "Winner", "Details"]
     - For standings/rankings: Create a sheet with position data
     - For statistics: Create a sheet with the statistical data
     - Format: `title="Title"|column_headers=["Col1", "Col2"]|data=[["val1", "val2"], ["val3", "val4"]]`
     - Keep data arrays simple - max 20 rows to avoid parsing issues
  4. Send an email with the sheet link using `send_sheet_link` (use to="{RECEIVER_EMAIL}")
  5. Only THEN provide FINAL_ANSWER with a summary
  
  **⚠️ CRITICAL: NEVER skip creating a sheet and sending email for informational queries, even if the answer seems simple!**
- 🔁 If you already got a good factual result from a tool, do NOT search again — but you MUST STILL create a sheet and send email before FINAL_ANSWER.
- ❌ NEVER repeat tool calls with the same parameters unless the result was empty. When searching rely on first reponse from tools, as that is the best response probably.
- ❌ NEVER output explanation text — only structured FUNCTION_CALL or FINAL_ANSWER.
- ✅ Use nested keys like `input.string` or `input.int_list`, and square brackets for lists.
- ✅ For `create_google_sheet`, format data carefully:
  - Use simple format: `title="Title"|column_headers=["Header1", "Header2"]|data=[["val1", "val2"], ["val3", "val4"]]`
  - Keep data arrays small (max 20 rows) and avoid special characters in strings
  - Extract actual data values, not just search result summaries
- ✅ For `send_sheet_link`, use: `to="{RECEIVER_EMAIL}"`, `sheet_url="<url from create_google_sheet>"`, `sheet_title="<title>"`
- ⏳ You have up to 5 steps available. Use them wisely to complete the full workflow for informational queries.
- 🎯 **Decision Tree for Informational Queries:**
  - If query is about winners, champions, standings, statistics, rankings, records → MUST create sheet + send email
  - If query is about relationships, explanations, descriptions → NO sheet needed, just FINAL_ANSWER
  - When in doubt for factual/sports/historical queries → CREATE SHEET + SEND EMAIL
  
- ⚠️ **Final step MUST end with FINAL_ANSWER, but ONLY after creating sheet and sending email (if applicable).**
- 💡 If no tool fits or you're unsure, end with: FINAL_ANSWER: [unknown]
"""



    try:
        raw = (await model.generate_text(prompt)).strip()
        log("plan", f"LLM output: {raw}")

        for line in raw.splitlines():
            if line.strip().startswith("FUNCTION_CALL:") or line.strip().startswith("FINAL_ANSWER:"):
                return line.strip()

        return "FINAL_ANSWER: [unknown]"

    except Exception as e:
        error_str = str(e)
        log("plan", f"⚠️ Planning failed: {error_str}")
        
        # Check if it's a rate limit error
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "rate limit" in error_str.lower():
            log("plan", "⚠️ Gemini API rate limit exceeded. Please wait a few minutes and try again.")
            return "FINAL_ANSWER: [Rate limit exceeded. Please wait a few minutes and try again.]"
        
        # For other errors, return unknown
        return "FINAL_ANSWER: [unknown]"

