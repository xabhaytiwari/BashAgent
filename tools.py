import os
import subprocess
from langchain_core.tools import tool

@tool
def execute_shell_command(command: str) -> str:
    """
    Executes a shell comman in the Git Bash/terminal environment.
    Use this to list files, read contents, or run scripts.
    
    :param command: Description
    :type command: str
    :return: Description
    :rtype: str
    """
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = result.stdout

        if result.stderr:
            output += f"\nError Output:\n{result.stderr}"
        
        return output if output.strip() else "Command executed succesfully with no ouput."
    except Exception as e:
        return f"Failed to execute command: {str(e)}"

@tool
def write_to_file(filepath: str, content: str) -> str:
    """
    Writes content to a file. Overwrites if it exists.
    Useful for creating scripts or saving code.
    """

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"