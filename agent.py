#!/usr/bin/env python
import sys
import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from tools import execute_shell_command, write_to_file

# Tools (Import from tools.py) {Later}
tools = [execute_shell_command, write_to_file]

# State Definition
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# LLM Setup
if not os.getenv("GOOGLE_API_KEY"):
    print("Warning: GOOGLE_API_KEY not set. API calls will fail.")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
llm_with_tools = llm.bind_tools(tools)

# Nodes
# "Brain" Node
def call_model(state: AgentState):
    """The main node that talks to the LLM"""
    # dynamic context
    cwd = os.getcwd()
    os_info = os.name

    system_prompt = SystemMessage(content=f"""
    You are a Bash Agent running on {os_info}.
    Current Working Directory: {cwd}
    
    When asked to perform tasks, generate the appropriate shell commands.
    Always check the output of your commands.
    """)

    # Prepend system message to history
    messages = [system_prompt] + state["messages"]

    return {"messages": [llm_with_tools.invoke(state["messages"])]}

# "Tools" Node
# def call_tool(state: AgentState):
   # """Will add functionality later"""
tool_node = ToolNode(tools)
# I will add others later

# Graph Builder
builder = StateGraph(AgentState)

builder.add_node("call_model", call_model)
builder.add_node("tools", tool_node)
builder.add_edge(START, "call_model")

# Conditional edge: If LLM asks for a tool -> go to 'tools', else -> END
builder.add_conditional_edges(
    "call_model",
    tools_condition,
)

builder.add_edge("tools", "call_model")

def run_chat(user_input, agent, config):
    """
    Handles a single turn of coversation, including the Human-in-the-Loop check.
    """
    events = agent.stream(
        {"messages": [HumanMessage(content=user_input)]},
        config=config
    )

    for event in events:
        if "call_model" in event:
            print(f"AI: {event['call_model']['messages'][-1].content}")
 
        # Human-in-the-Loop
    snapshot = agent.get_state(config) # If agent is paused
    if snapshot.next: # contains the name of the next node
        # Add step asking user for permission
        try:
            last_message = snapshot.values["messages"][-1]
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
            
            print(f"   Tool: {tool_name}")
            print(f"   Args: {tool_args}")
            # We use stderr for the prompt so it doesn't get mixed with pipe output if you pipe data later
            print("Agent wants to execute this command. Approve? (y/n): ", end="", flush=True)
            user_approval = input()
        except EOFError:
            user_approval = "n"

        if user_approval.lower() == 'y':
            print("Executing...")
            # Resume execution by passing None
            for event in agent.stream(None, config=config):
                if "call_model" in event:
                    print(f"AI: {event['call_model']['messages'][-1].content}")
                if "tools" in event:
                    print(f"Tool Output: {event['tools']['messages'][-1].content}")
        else:
            print("Action Cancelled")

if __name__ == "__main__":
    print("Agent Online. Type 'quit' to exit.")
    
    with sqlite3.connect("memory.db", check_same_thread=False) as conn:
        memory = SqliteSaver(conn)
        
        # Compile with interrupt
        agent = builder.compile(checkpointer=memory, interrupt_before=["tools"])
        
        # Shared session ID means the agent remembers previous CLI commands!
        config = {"configurable": {"thread_id": "main_session"}}

        # Are there command line arguments?
        # sys.argv[0] is the script name, sys.argv[1:] are the arguments
        if len(sys.argv) > 1:
            # CLI MODE: User typed "ai create a file..."
            query = " ".join(sys.argv[1:])
            run_chat(query, agent, config)
        else:
            # INTERACTIVE MODE: User just typed "bashagent"
            print("Bash Agent Online. Type 'quit' to exit.")
            while True:
                try:
                    user_input = input("You: ")
                    if user_input.lower() in ["quit", "exit"]:
                        break
                    run_chat(user_input, agent, config)
                except KeyboardInterrupt:
                    break

