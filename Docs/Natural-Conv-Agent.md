# Roadmap for a Natural Conversational Voice Agent

We currently have a working call flow (greeting → request intent → ask for name/DOB → verify → answer) with <2s latency. Now we will focus on making the conversation flow feel *natural* and handle multi-turn interactions. The plan below confirms the suggested approach is feasible and outlines detailed implementation phases, safety measures, and tooling. We will also note industry best practices and consider frameworks like MCP or LangChain for future expansion.

## Phase 1: State-Machine Conversation Flow  
**Goal:** Implement a deterministic dialog controller to simulate a natural phone support call. This is fully achievable with standard code (no heavy AI needed yet).  

- **Greeting:** Detect if the user just says “hi”, “hello”, etc. If so, respond with a welcome prompt (e.g. “Hi! How can I help you today?”). This can be done with simple keyword matching on the first turn.  
- **Intent Recognition:** Check if the user’s first request involves order inquiries (like “order status”, “my package”, etc.). If the user asks for status **before** giving identity, respond with: “Sure, I can check that. Please tell me your full name and date of birth.”  
- **Collect Identity:** If only one of name or DOB is given (e.g. user says “My name is John Doe”), prompt for the missing piece: “Thanks, and what is your date of birth?” Vice versa if DOB was given first.  
- **Verification and Answer:** Once both name and DOB are collected, verify them against the database. Use a **parameterized SELECT** query (or ORM) to avoid injections. For now, do **only SELECT** queries; explicitly disable DELETE/TRUNCATE/DROP in the code. E.g., `cursor.execute("SELECT status FROM orders WHERE name=%s AND dob=%s AND deleted_at IS NULL", (name, dob))`.  
- **Response:** If the order is found, speak the status (e.g. “Your last order is on its way and will arrive tomorrow.”). If not found, say “I’m sorry, I could not find any order matching your name and DOB.”. Always use friendly, polite language.  
- **Follow-ups:** After answering, ask if the user needs anything else (“Is there anything else I can help you with?”). If yes, loop back to collecting the next intent. If no, thank the user and hang up.  

*Implementation Details:* This flow is essentially a finite state machine with states like `GREETING`, `ASK_INTENT`, `ASK_NAME`, `ASK_DOB`, `VERIFY`, `ANSWER`, and `DONE`. You can code this with a simple Python class (e.g. `ConversationState`) storing `state`, `name`, `dob`, and `intent`. After each user utterance (transcribed to text), update the state and produce the next TwiML response. Using a state machine explicitly ensures the agent doesn’t jump ahead.  

**Best Practices:** According to voice-agent guidelines, the LLM (if used later) should know its input comes from ASR and output goes to TTS【56†L267-L276】. Even now, craft responses suitable for speech (short, clear sentences). Use **voice activity detection (VAD)** to tell when the user stops speaking, and only then proceed【56†L287-L295】. Also plan for **interruption handling** – if the user cuts in while the agent is talking, stop the speech output immediately【56†L308-L312】.  

## Phase 2: Session Memory for Multi-Turn Interactions  
**Goal:** Keep context across multiple turns in the same call so the user can ask follow-up questions naturally.  

- **In-Memory Session:** Maintain a session object (persisted for the duration of the call) that stores fields like `{ name, dob, intent, last_response }`. Upon the first successful name/DOB verification, store them. This way, if the user asks another question (“Also, what’s the delivery date?”), you already have their identity. LangChain/LangGraph documentation shows that agents can manage short-term memory in their state【64†L98-L101】. We will implement our own simple version in code (e.g. a dictionary keyed by CallSID).  
- **Follow-up Flow:** After answering an intent, loop back to check if the user has another question. Use the stored `intent` or simply read the next user utterance. For example, if the user says “Also, will it arrive by Friday?”, interpret it relative to the current context (order inquiry). If the follow-up requires new info (e.g. a different order ID), request it.  
- **Switching Intent:** If the user requests a different task mid-call (e.g. “I also want to change my address”), you can either handle it (see Phase 3) or tell them it’s not supported yet.  
- **Call Persistence:** This memory lives only for the call. Once the call ends, the session resets. (In future, you could implement account linking for returning callers, but not needed now.)  

This multi-turn memory makes the conversation natural. It’s basically keeping state between steps of the finite state machine. The memory won’t survive across calls unless you add persistent user profiles, which is outside scope for now.

## Phase 3: Basic Intent and NLU Expansion  
**Goal:** Handle more varied user requests beyond “order status” with simple understanding.  

- **Define Intents:** Identify common intents relevant to order support, such as: _OrderStatus_, _DeliveryDate_, _CancelOrder_, _ChangeAddress_, _GeneralInquiry_. Create a list of keywords/phrases for each (e.g. “cancel my order”, “delivery date”, “hello”, “help with my order”, etc.).  
- **Pattern Matching:** Use simple logic or regex to classify the user’s utterance into one of these intents. For example, if the text contains “status” or “order number” then `intent=OrderStatus`; if it contains “cancel” then `intent=CancelOrder`, etc. This can be a series of `if` statements or a small rule-based engine.  
- **Fallback:** If the intent isn’t recognized, respond with a polite fallback: “I’m sorry, I’m not able to help with that at the moment. Can you ask something about your orders?” This ensures the agent doesn’t hallucinate or say something irrelevant.  
- **Follow-Up Questions:** For each intent, specify what additional info is needed. (E.g. for _CancelOrder_, you would ask which order to cancel, and then verify name/DOB if not already done.)  
- **No LLM for Intent:** At this stage, do **not** use an LLM to classify intent – it could misinterpret or hallucinate. Keep the logic transparent and testable.

This simple NLU expansion is safe and predictable. It maps well to the state machine (different flows for different intents). In future, you could add an LLM or classifier to assist with understanding synonyms, but carefully restrict its use.

## Phase 4: Controlled LLM Assistance for Responses  
**Goal:** Use an LLM sparingly to make the agent’s language more natural, without letting it alter logic or access data unsafely.  

- **Role of LLM:** The LLM should **only** rephrase or expand the reply text after the answer is determined. For example, after retrieving the order status, you might call the LLM with a prompt like:  
  ```
  system: The user is talking on a phone call. Your input is from a speech-to-text system.
  user: Their full name is John Doe and DOB is 1990-01-01, order status is "shipped and arrives May 5".
  assistant: 
  ```  
  Then use the LLM’s answer as the spoken response. Emphasize in the system message that output will be spoken, so it should use short, clear sentences【56†L267-L276】.  
- **Guardrails:** Do not allow the LLM to generate SQL or logic. For example, set the system prompt to: “You are a customer support assistant. Answer only using the provided facts about the user’s order. If information is missing, ask for it.” This ensures the LLM only transforms known data.  
- **No Direct Tool Access:** The LLM should not directly query the database. It should only get answer data fed into it. All database queries remain done in our code (using SELECTs). This prevents injection or data leakage.  
- **Hallucination Safety:** Since LLMs can hallucinate, double-check any critical data. E.g., after the LLM speaks the reply, you could have a final check that the key facts (like delivery date) match your database result, to guard against mistakes.  
- **Human-like Language:** Using the LLM can make responses more conversational and varied (“Sure, [Name]. I see your order is on the way to you.”). This helps simulate a human agent.

Overall, this phase carefully adds AI to improve naturalness without compromising control. The system architecture remains rule-based at its core, with the LLM acting like a polite rephraser.

## Database and Safety Practices  
- **Safe Queries:** Use parameterized queries or an ORM to prevent injection. For example, in Python:  
  ```python
  cursor.execute("SELECT status FROM orders WHERE name=%s AND dob=%s AND deleted_at IS NULL", (name, dob))
  ```  
  Never concatenate user input into SQL strings.  
- **Read-only by Default:** As suggested, allow only SELECT queries in the normal flow. We can build future UPDATE/INSERT for actions like address change, but only on specific columns. All such queries should use whitelists of allowed fields.  
- **Soft Delete:** Modify the `orders` table to include a `deleted_at` (timestamp) or `is_deleted` flag. In all queries, add `WHERE deleted_at IS NULL` to ignore deleted records. This way, when we later implement deletion, it won’t remove data entirely (soft-delete).  
- **Audit Logging:** It can be helpful to log each completed SQL query and the corresponding user query (sanitized). This aids debugging and security audits.  
- **No Privilege Escalation:** Do not give the voice agent elevated DB permissions. Use a DB user with minimal rights (only SELECT/UPDATE on allowed tables).  
- **Validation:** After retrieval, validate data types and ranges (e.g. check that the returned DOB matches format) before proceeding. This adds a safety layer.

These steps ensure our “query builder” is robust and cannot do harmful operations.

## Tools, Frameworks, and Infrastructure  
- **MCP (Model Context Protocol):** The OpenAI **MCP** framework is a modern way to connect LLMs with external tools (databases, APIs) via a standard protocol【59†L585-L594】. It’s great for complex agents. In our current project, implementing a full MCP agent is **not required** – we can make direct database calls safely ourselves. If in future we build a more autonomous voice agent with many tools, we could switch to an MCP-based architecture for modularity.  
- **LangChain / LangGraph:** These frameworks offer conversation chaining, memory, and tool calling. For example, LangGraph can persist short-term memory as part of the agent state【64†L98-L101】. However, at our current stage, they are likely overkill. A custom state machine gives us more direct control and fewer moving parts. If we expand to a more complex multi-agent system later, LangChain’s abstractions (memory, agents, LLM integration) might be useful. For now, we will implement the logic manually for clarity and simplicity.  
- **Other Tools:** No additional frameworks are strictly needed. We can continue using FastAPI, Twilio’s SDK, and perhaps add a small NLU library if needed (like spaCy or a regex engine). Keep the stack lightweight.  

## Additional Best Practices and Next Steps  
- **Testing:** Create unit tests or scripts simulating phone calls. Test scenarios: only greeting, only name, missing info, multiple questions, unknown intent, etc. This will uncover logic holes.  
- **Logging & Monitoring:** Log the dialogue turns and state changes to detect any issues. Measure latency again in this multi-turn mode to ensure it stays acceptable.  
- **User Experience:** Ensure quick responses. If any step is slow (e.g. LLM), consider playing a short “thinking” sound or saying “One moment please.”  
- **Interruption Handling:** If the user interrupts the agent while it’s speaking, Twilio can stop the speech. Implement this so the agent doesn’t talk over the user【56†L308-L312】.  
- **Future Intents:** You may later add more intents (e.g. billing questions). Each would follow the same phased approach (detect intent → collect any needed info → answer).  
- **Review Flow:** After implementing each phase, review with real users or stakeholders. Adjust phrasing, add new fallbacks, and refine the state transitions as needed.

**Summary of Achievements:** This phased plan is practical and incremental. It starts with a simple rule-based engine (achievable now) and gradually adds flexibility. Industry best practices back up our choices (e.g. VAD and context aware prompting【56†L287-L295】【56†L308-L312】). Tools like MCP or LangChain could be considered in future, but are not needed at the start. Following this roadmap will result in a more human-like, multi-turn voice agent while keeping it safe and maintainable.

