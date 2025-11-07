# core/loop.py

import asyncio
from core.context import AgentContext
from core.session import MultiMCP
from core.strategy import decide_next_action
from modules.perception import extract_perception, PerceptionResult
from modules.action import ToolCallResult, parse_function_call
from modules.memory import MemoryItem
import json


class AgentLoop:
    def __init__(self, user_input: str, dispatcher: MultiMCP):
        self.context = AgentContext(user_input)
        self.mcp = dispatcher
        self.tools = dispatcher.get_all_tools()

    def tool_expects_input(self, tool_name: str) -> bool:
        # Handle both tool objects (stdio) and tool dicts (SSE)
        tool = None
        for t in self.tools:
            # Check if it's a dict (SSE) or object (stdio)
            if isinstance(t, dict):
                if t.get("name") == tool_name:
                    tool = t
                    break
            else:
                if getattr(t, "name", None) == tool_name:
                    tool = t
                    break
        
        if not tool:
            return False
        
        # Get parameters - handle both dict and object
        if isinstance(tool, dict):
            parameters = tool.get("inputSchema", {}).get("properties", {})
        else:
            parameters = getattr(tool, "parameters", {})
            # If parameters is a dict with 'properties', extract it
            if isinstance(parameters, dict) and "properties" in parameters:
                parameters = parameters["properties"]
        
        return list(parameters.keys()) == ["input"]

    async def _ensure_email_sent(self, max_retries: int = 3):
        """
        Ensure email is sent after sheet creation, with retry logic.
        
        This is a safety net to catch cases where:
        - Email sending failed during the main loop but wasn't retried
        - The agent reached FINAL_ANSWER before sending email
        - Transient errors occurred (network issues, rate limits, etc.)
        
        Uses exponential backoff (1s, 2s, 4s) between retries.
        """
        import asyncio
        import config
        
        receiver_email = getattr(config, 'RECEIVER_EMAIL', 'dbvb2k.aws@gmail.com')
        
        for attempt in range(max_retries):
            try:
                print(f"[email-retry] Attempt {attempt + 1}/{max_retries} to send email...")
                
                # Call send_sheet_link tool
                response = await self.mcp.call_tool("send_sheet_link", {
                    "to": receiver_email,
                    "sheet_url": self.context.sheet_url,
                    "sheet_title": self.context.sheet_title or "Google Sheet"
                })
                
                # Check if email was sent successfully
                # Response.content can be a list of TextContent objects or a single object
                if hasattr(response, 'content'):
                    if isinstance(response.content, list) and len(response.content) > 0:
                        # Get text from first content item
                        raw = getattr(response.content[0], 'text', str(response.content[0]))
                    else:
                        raw = getattr(response.content, 'text', str(response.content))
                else:
                    raw = str(response)
                
                try:
                    # Try to parse as JSON first
                    result_obj = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else raw
                except (json.JSONDecodeError, AttributeError):
                    result_obj = raw
                
                # Extract result string
                if isinstance(result_obj, dict):
                    result_str = str(result_obj.get("status", ""))
                else:
                    result_str = str(result_obj)
                
                status_lower = result_str.lower()
                
                # Check if email was sent successfully
                if ("sent" in status_lower or "simulated" in status_lower) and "failed" not in status_lower:
                    self.context.email_sent = True
                    print(f"[email-retry] ✅ Email sent successfully on attempt {attempt + 1}: {result_str}")
                    return
                elif "failed" in status_lower:
                    print(f"[email-retry] ❌ Email failed on attempt {attempt + 1}: {result_str}")
                    # Will retry if attempts remain
                else:
                    print(f"[email-retry] ⚠️ Email status unclear on attempt {attempt + 1}: {result_str}")
                    # If status is unclear but no error, consider it success to avoid infinite retries
                    if "error" not in status_lower and "exception" not in status_lower:
                        self.context.email_sent = True
                        print(f"[email-retry] ✅ Assuming success based on unclear status")
                        return
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[email-retry] ❌ Attempt {attempt + 1} failed: {error_msg}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff: wait 1s, 2s, 4s
                    wait_time = 2 ** attempt
                    print(f"[email-retry] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[email-retry] ❌ All {max_retries} attempts failed. Email not sent.")
                    # Log this failure but don't raise - we've tried our best

    async def run(self) -> str:
        print(f"[agent] Starting session: {self.context.session_id}")

        try:
            max_steps = self.context.agent_profile.max_steps
            query = self.context.user_input

            for step in range(max_steps):
                self.context.step = step
                print(f"[loop] Step {step + 1} of {max_steps}")

                # 🧠 Perception
                perception_raw = await extract_perception(query)


                # ✅ Exit cleanly on FINAL_ANSWER
                # ✅ Handle string outputs safely before trying to parse
                if isinstance(perception_raw, str):
                    pr_str = perception_raw.strip()
                    
                    # Clean exit if it's a FINAL_ANSWER
                    if pr_str.startswith("FINAL_ANSWER:"):
                        self.context.final_answer = pr_str
                        break

                    # Detect LLM echoing the prompt
                    if "Your last tool produced this result" in pr_str or "Original user task:" in pr_str:
                        print("[perception] ⚠️ LLM likely echoed prompt. No actionable plan.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break

                    # Try to decode stringified JSON if it looks valid
                    try:
                        perception_raw = json.loads(pr_str)
                    except json.JSONDecodeError:
                        print("[perception] ⚠️ LLM response was neither valid JSON nor actionable text.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break


                # ✅ Try parsing PerceptionResult
                if isinstance(perception_raw, PerceptionResult):
                    perception = perception_raw
                else:
                    try:
                        # Attempt to parse stringified JSON if needed
                        if isinstance(perception_raw, str):
                            perception_raw = json.loads(perception_raw)
                        perception = PerceptionResult(**perception_raw)
                    except Exception as e:
                        print(f"[perception] ⚠️ LLM perception failed: {e}")
                        print(f"[perception] Raw output: {perception_raw}")
                        break

                print(f"[perception] Intent: {perception.intent}, Hint: {perception.tool_hint}")

                # 💾 Memory Retrieval
                retrieved = self.context.memory.retrieve(
                    query=query,
                    top_k=self.context.agent_profile.memory_config["top_k"],
                    type_filter=self.context.agent_profile.memory_config.get("type_filter", None),
                    session_filter=self.context.session_id
                )
                print(f"[memory] Retrieved {len(retrieved)} memories")

                # 📊 Planning (via strategy)
                plan = await decide_next_action(
                    context=self.context,
                    perception=perception,
                    memory_items=retrieved,
                    all_tools=self.tools
                )
                print(f"[plan] {plan}")

                if "FINAL_ANSWER:" in plan:
                    # Optionally extract the final answer portion
                    final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                    if final_lines:
                        self.context.final_answer = final_lines[-1].strip()
                    else:
                        self.context.final_answer = "FINAL_ANSWER: [result found, but could not extract]"
                    break


                # ⚙️ Tool Execution
                try:
                    tool_name, arguments = parse_function_call(plan)

                    if self.tool_expects_input(tool_name):
                        tool_input = {'input': arguments} if not (isinstance(arguments, dict) and 'input' in arguments) else arguments
                    else:
                        tool_input = arguments

                    response = await self.mcp.call_tool(tool_name, tool_input)

                    # ✅ Safe TextContent parsing
                    # Response.content can be a list of TextContent objects or a single object
                    if hasattr(response, 'content'):
                        if isinstance(response.content, list) and len(response.content) > 0:
                            # Get text from first content item
                            raw = getattr(response.content[0], 'text', str(response.content[0]))
                        else:
                            raw = getattr(response.content, 'text', str(response.content))
                    else:
                        raw = str(response)
                    
                    try:
                        # Try to parse as JSON first
                        result_obj = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else raw
                    except (json.JSONDecodeError, AttributeError):
                        result_obj = raw
                    
                    # Extract result string for display
                    if isinstance(result_obj, dict):
                        # Try multiple possible keys
                        result_str = (result_obj.get("markdown") or 
                                    result_obj.get("text") or 
                                    result_obj.get("sheet_url") or
                                    json.dumps(result_obj, indent=2))
                    else:
                        result_str = str(result_obj)
                    
                    print(f"[action] {tool_name} → {result_str[:200]}...")

                    # Track sheet creation
                    if tool_name == "create_google_sheet":
                        try:
                            # Extract sheet URL and title from result
                            # The response can be in multiple formats depending on transport
                            sheet_url_extracted = None
                            sheet_title_extracted = None
                            
                            # Try to extract from dict result_obj
                            if isinstance(result_obj, dict):
                                # Direct keys
                                sheet_url_extracted = (result_obj.get("sheet_url") or 
                                                     result_obj.get("url"))
                                
                                # Try nested content list (SSE response format)
                                if not sheet_url_extracted:
                                    content_list = result_obj.get("content", [])
                                    if isinstance(content_list, list) and len(content_list) > 0:
                                        first_content = content_list[0]
                                        if isinstance(first_content, dict):
                                            content_text = first_content.get("text", "")
                                            # Try to parse JSON from content text
                                            try:
                                                content_obj = json.loads(content_text)
                                                if isinstance(content_obj, dict):
                                                    sheet_url_extracted = content_obj.get("sheet_url") or content_obj.get("url")
                                                    if not sheet_title_extracted:
                                                        sheet_title_extracted = content_obj.get("worksheet_name") or content_obj.get("title")
                                            except:
                                                pass
                                            # Also search for URL in text
                                            if not sheet_url_extracted:
                                                import re
                                                url_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+', content_text)
                                                if url_match:
                                                    sheet_url_extracted = url_match.group(0)
                                
                                # Parse from text content if still not found
                                if not sheet_url_extracted and "text" in result_obj:
                                    import re
                                    url_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+', str(result_obj["text"]))
                                    if url_match:
                                        sheet_url_extracted = url_match.group(0)
                            
                            # Try to extract from string result
                            if not sheet_url_extracted and isinstance(result_str, str):
                                import re
                                # Look for Google Sheets URL pattern
                                url_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+', result_str)
                                if url_match:
                                    sheet_url_extracted = url_match.group(0)
                            
                            # Extract title from arguments
                            if isinstance(arguments, dict):
                                sheet_title_extracted = (arguments.get("title") or 
                                                       arguments.get("input", {}).get("title") if isinstance(arguments.get("input"), dict) else None)
                            
                            # Also try to extract title from result
                            if not sheet_title_extracted:
                                import re
                                title_match = re.search(r'"title":\s*"([^"]+)"', str(result_str))
                                if not title_match:
                                    title_match = re.search(r'title[=:]\s*"([^"]+)"', str(result_str))
                                if title_match:
                                    sheet_title_extracted = title_match.group(1)
                            
                            # Store if we found a URL
                            if sheet_url_extracted:
                                self.context.sheet_url = sheet_url_extracted
                                self.context.sheet_created = True
                                if sheet_title_extracted:
                                    self.context.sheet_title = sheet_title_extracted
                                print(f"[tracking] Sheet created: {self.context.sheet_url} (title: {self.context.sheet_title})")
                            else:
                                print(f"[tracking] Could not extract sheet_url from result. Result type: {type(result_obj)}, Result: {result_str[:200]}")
                        except Exception as e:
                            print(f"[tracking] Could not extract sheet info: {e}")
                            import traceback
                            print(f"[tracking] Traceback: {traceback.format_exc()}")
                    
                    # Track email sending
                    if tool_name == "send_sheet_link" or tool_name == "send_email":
                        try:
                            # Check if email was successfully sent
                            status_str = str(result_str).lower()
                            if isinstance(result_obj, dict):
                                status = str(result_obj.get("status", "")).lower()
                                message_id = str(result_obj.get("message_id", ""))
                                
                                # Check for success indicators
                                if ("sent" in status or "simulated" in status) and "failed" not in status:
                                    self.context.email_sent = True
                                    print(f"[tracking] ✅ Email sent successfully: {status} (message_id: {message_id})")
                                elif "failed" in status or "failed" in message_id.lower():
                                    print(f"[tracking] ❌ Email failed: {status}")
                                    # Don't set email_sent = True, so post-processing can retry
                                else:
                                    print(f"[tracking] ⚠️ Email status unclear: {status}")
                            elif "sent" in status_str and "failed" not in status_str:
                                self.context.email_sent = True
                                print(f"[tracking] ✅ Email sent (from string): {result_str[:100]}")
                            elif "failed" in status_str:
                                print(f"[tracking] ❌ Email failed (from string): {result_str[:100]}")
                        except Exception as e:
                            print(f"[tracking] Could not verify email status: {e}")
                            import traceback
                            print(f"[tracking] Traceback: {traceback.format_exc()}")

                    # 🧠 Add memory
                    memory_item = MemoryItem(
                        text=f"{tool_name}({arguments}) → {result_str}",
                        type="tool_output",
                        tool_name=tool_name,
                        user_query=query,
                        tags=[tool_name],
                        session_id=self.context.session_id
                    )
                    self.context.add_memory(memory_item)

                    # 🔁 Next query
                    query = f"""Original user task: {self.context.user_input}

    Your last tool produced this result:

    {result_str}

    If this fully answers the task, return:
    FINAL_ANSWER: your answer

    Otherwise, return the next FUNCTION_CALL."""
                except Exception as e:
                    error_msg = str(e)
                    print(f"[error] Tool execution failed: {e}")
                    
                    # For email sending errors, don't break the loop - log and continue
                    # This allows the agent to try again or complete other steps
                    if "send_sheet_link" in error_msg.lower() or "send_email" in error_msg.lower() or "gmail" in error_msg.lower():
                        print(f"[warning] Email sending failed, but continuing: {error_msg}")
                        # Add error to memory so agent knows email failed
                        error_memory = MemoryItem(
                            text=f"Email sending failed: {error_msg}",
                            type="tool_error",
                            tool_name="send_sheet_link",
                            user_query=query,
                            tags=["email_error"],
                            session_id=self.context.session_id
                        )
                        self.context.add_memory(error_memory)
                        # Update query to include error info
                        query = f"""Original user task: {self.context.user_input}

Your last tool (email sending) failed with error: {error_msg}

Please try to send the email again or return FINAL_ANSWER if you cannot."""
                        continue
                    
                    # For other critical errors, break the loop
                    break

        except Exception as e:
            print(f"[agent] Session failed: {e}")

        # 🔄 Post-processing: Ensure email is sent if sheet was created
        if self.context.sheet_created and not self.context.email_sent and self.context.sheet_url:
            print(f"[post-processing] Sheet created but email not sent. Attempting to send email...")
            await self._ensure_email_sent()

        return self.context.final_answer or "FINAL_ANSWER: [no result]"


