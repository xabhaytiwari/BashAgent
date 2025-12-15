import os
import sqlite3
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from tools import execute_shell_command

# Tools (Import from tools.py) {Later}
tools = [execute_shell_command]

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


if __name__ == "__main__":
    print("🤖 Agent Online. Type 'quit' to exit.")
    
    with sqlite3.connect("memory.db", check_same_thread=False) as conn:
        memory_saver = SqliteSaver(conn)
        agent = builder.compile(checkpointer=memory_saver)
    
    # This config acts as the "Session ID"
    # Change 'thread_id' to start a fresh conversation
    config = {"configurable": {"thread_id": "session_1"}}

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break

        # Stream the output so you see steps as they happen
        events = agent.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )

        for event in events:
            if "chatbot" in event:
                print(f"AI: {event['chatbot']['messages'][-1].content}")
            if "tools" in event:
                print(f"Tool Output: {event['tools']['messages'][-1].content}")