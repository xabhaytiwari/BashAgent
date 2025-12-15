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

# Styling (sundarta is important!)
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status

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

console = Console()

def run_chat(user_input, agent, config):
    """
    Handles a single turn of coversation, including the Human-in-the-Loop check.
    """
    # Divide the execution in phases, to be modular with "Styling"

    # Initial Exectuion (Thinking Phase)
    # Spinner (Ashwin Anna)

    with console.status("[bold green]Thinking...", spinner="dots"):    
        events = agent.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )
        
        ai_response =""
        for event in events:
            if "call_model" in event:
                ai_response = event['call_model']['messages'][-1].content

    if ai_response:
        console.print(Panel(Markdown(ai_response)), title="AI", border_style="blue")

    # Human-in-the-Loop (Approval Phase)
    snapshot = agent.get_state(config) # If agent is paused
    if snapshot.next: # contains the name of the next node
        # Add step asking user for permission
        try:
            last_message = snapshot.values["messages"][-1]
            console.print("\n[bold yellow] Agent Paused. Planned Actions:[/bold yellow]")
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
            
            console.print(f"   Tool: {tool_call['name']}")
            console.print(f"   Args: {tool_call['args']}")
            # We use stderr for the prompt so it doesn't get mixed with pipe output if you pipe data later
            print("Agent wants to execute this command. Approve? (y/n): ", end="", flush=True)
            user_approval = input()
        except EOFError:
            user_approval = "n"

        # Doing Phase
        if user_approval.lower() == 'y':
            with console.status("[bold red]Executing...", spinner="grenade"):
            # Resume execution by passing None
                for event in agent.stream(None, config=config):
                    if "call_model" in event:
                        response = event['call_model']['messages'][-1].content
                        console.print(Panel(Markdown(response), title="AI", border_style="blue"))
                    if "tools" in event:
                        # Tool Output
                        output = event['tools']['messages'][-1].content
                        # Truncate long outputs for display to avoid flooding terminal
                        display_output = output[:500] + "..." if len(output) > 500 else output
                        console.print(Panel(display_output, title="⚙️ Tool Output", border_style="dim white"))
        else:
            console.print("[bold red] Uh Oh, Action Cancelled[/bold red]")

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

