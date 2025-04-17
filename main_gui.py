import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import os
import json
import threading
import queue
from pathlib import Path
from openai import OpenAI, APIError, RateLimitError
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables (optional, if using a .env file)
load_dotenv()

# Check for API key
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("Error: OPENAI_API_KEY environment variable not set.")
    # Optionally use simpledialog to ask for the key if not set
    API_KEY = simpledialog.askstring("API Key Required", "Enter your OpenAI API Key:", show='*')
    if not API_KEY:
        messagebox.showerror("API Key Error", "OpenAI API Key is required to run the application.")
        exit() # Exit if still no key

# Initialize OpenAI client
try:
    client = OpenAI(api_key=API_KEY)
    # Test connection (optional, but good practice)
    # client.models.list() # This call can verify the key early
except APIError as e:
     messagebox.showerror("OpenAI API Error", f"Failed to initialize OpenAI client: {e}")
     exit()
except Exception as e:
    messagebox.showerror("Error", f"An unexpected error occurred during OpenAI client initialization: {e}")
    exit()

# --- Tool Functions ---

def read_file(path: str) -> str:
    """
    Read the contents of a given relative file path.
    Use this when you want to see what's inside a file.
    Do not use this with directory names.
    Returns the file content as a string or an error message.
    """
    try:
        file_path = Path(path).resolve()
        # Basic security check: prevent reading files outside the current working dir tree
        # You might want stricter checks depending on your use case.
        if not file_path.is_relative_to(Path.cwd().resolve()):
             return f"Error: Access denied. Can only read files within the current project directory: {Path.cwd()}"
        if not file_path.is_file():
            return f"Error: Path '{path}' is not a file or does not exist."
        content = file_path.read_text(encoding='utf-8')
        # Truncate long files to avoid excessive token usage / overly long responses
        max_len = 10000 # Adjust as needed
        if len(content) > max_len:
             return content[:max_len] + "\n\n[... File truncated due to length ...]"
        return content
    except FileNotFoundError:
        return f"Error: File not found at path '{path}'"
    except PermissionError:
        return f"Error: Permission denied to read file '{path}'"
    except Exception as e:
        return f"Error reading file '{path}': {str(e)}"

def list_files(path: str = ".") -> str:
    """
    List files and directories at a given relative path.
    If no path is provided, lists files in the current directory.
    Returns a JSON string representing a list of files/directories,
    or an error message. Directories are marked with a trailing '/'.
    """
    try:
        base_path = Path(path).resolve()
        # Basic security check
        if not base_path.is_relative_to(Path.cwd().resolve()):
             return f"Error: Access denied. Can only list files within the current project directory: {Path.cwd()}"
        if not base_path.is_dir():
            return f"Error: Path '{path}' is not a directory or does not exist."

        items = []
        max_items = 200 # Limit the number of items listed
        count = 0
        for item in base_path.iterdir():
            if count >= max_items:
                 items.append("[... Directory listing truncated due to size ...]")
                 break
            # Construct relative path from the *original* potentially relative input path
            # This avoids exposing absolute paths in the listing
            rel_path = Path(path) / item.name
            if item.is_dir():
                items.append(f"{rel_path}/")
            else:
                items.append(str(rel_path))
            count += 1

        return json.dumps(items) # Return as a JSON string for the LLM
    except FileNotFoundError:
        return f"Error: Directory not found at path '{path}'"
    except PermissionError:
        return f"Error: Permission denied to list directory '{path}'"
    except Exception as e:
        return f"Error listing files in '{path}': {str(e)}"

def create_new_file(file_path_str: str, content: str) -> str:
    """Helper to create a new file and necessary directories."""
    try:
        file_path = Path(file_path_str).resolve()
        # Security check
        if not file_path.is_relative_to(Path.cwd().resolve()):
             return f"Error: Access denied. Can only create files within the current project directory: {Path.cwd()}"

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return f"Successfully created file {file_path_str}"
    except PermissionError:
        return f"Error: Permission denied to create file or directory for '{file_path_str}'"
    except Exception as e:
        return f"Error creating file '{file_path_str}': {str(e)}"

def edit_file(path: str, old_str: str, new_str: str) -> str:
    """
    Make edits to a text file by replacing occurrences of 'old_str' with 'new_str'.
    'old_str' and 'new_str' MUST be different.
    If the file specified with path doesn't exist AND 'old_str' is empty, it will be created with 'new_str' as content.
    Returns 'OK' on success or an error message.
    """
    if old_str == new_str:
        return "Error: 'old_str' and 'new_str' must be different for editing."
    if not path:
        return "Error: 'path' cannot be empty."

    try:
        file_path = Path(path).resolve()
        # Security check
        if not file_path.is_relative_to(Path.cwd().resolve()):
             return f"Error: Access denied. Can only edit files within the current project directory: {Path.cwd()}"

        # Handle file creation case
        if not file_path.exists():
            if old_str == "":
                return create_new_file(path, new_str)
            else:
                return f"Error: File not found at path '{path}' and 'old_str' is not empty (cannot replace in non-existent file)."

        # Handle file editing case
        if not file_path.is_file():
            return f"Error: Path '{path}' exists but is not a file."

        original_content = file_path.read_text(encoding='utf-8')

        # The OpenAI model might send escaped newlines, etc. try to handle common cases
        # This might need refinement based on observed model behavior
        processed_old_str = old_str.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        processed_new_str = new_str.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')

        # Check if old_str exists before replacing
        if processed_old_str != "" and processed_old_str not in original_content:
             # Offer suggestions if minor differences exist (e.g., whitespace)
             if old_str.strip() in original_content:
                 return f"Error: 'old_str' ('{old_str}') not found exactly in file. Did you mean '{old_str.strip()}' (ignoring leading/trailing whitespace)?"
             # Add more fuzzy matching or suggestions if needed
             return f"Error: 'old_str' ('{old_str}') not found exactly in file '{path}'. Replacement aborted."


        new_content = original_content.replace(processed_old_str, processed_new_str)

        # Prevent accidental no-op writes if replacement didn't change anything
        # (This check is only meaningful if old_str was supposed to be found)
        if processed_old_str != "" and new_content == original_content:
            # This case should ideally be caught by the "not found" check above,
            # but serves as a fallback.
            return f"Warning: Replacing '{old_str}' with '{new_str}' resulted in no changes to the file '{path}'. Check if 'old_str' exists."


        file_path.write_text(new_content, encoding='utf-8')
        return "OK" # Simple confirmation

    except FileNotFoundError:
        # Should be handled by the creation logic, but catch just in case
        return f"Error: File not found at path '{path}'"
    except PermissionError:
        return f"Error: Permission denied to read or write file '{path}'"
    except Exception as e:
        return f"Error editing file '{path}': {str(e)}"


# --- Tool Definitions for OpenAI ---
# Map tool names to functions
available_tools = {
    "read_file": read_file,
    "list_files": list_files,
    "edit_file": edit_file,
}

# Define tools in OpenAI's required format
tools_openai_format = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a given relative file path. Use this when you want to see what's inside a file. Do not use this with directory names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative path of a file in the working directory.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given relative path. If no path is provided, lists files in the current directory. Directories are marked with a trailing '/'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional relative path to list files from. Defaults to current directory '.' if not provided.",
                    },
                },
                "required": [], # Path is optional
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Make edits to a text file by replacing ALL occurrences of 'old_str' with 'new_str'. 'old_str' and 'new_str' MUST be different. If the file specified with path doesn't exist AND 'old_str' is an empty string, it will be created with 'new_str' as content. USE WITH CAUTION.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative path to the file.",
                    },
                     "old_str": {
                        "type": "string",
                        "description": "Text to search for. Must match exactly. Use an empty string \"\" to create a new file if it doesn't exist.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Text to replace ALL occurrences of old_str with.",
                    },
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    }
]


# --- Agent Class ---
class CodeAgentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Code Editing Agent (OpenAI)")
        # Get screen dimensions for centering
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        # Set window size
        window_width = 800
        window_height = 600
        # Calculate position x, y coordinates
        x = (screen_width/2) - (window_width/2)
        y = (screen_height/2) - (window_height/2)
        root.geometry(f'{window_width}x{window_height}+{int(x)}+{int(y)}')

        self.conversation_history = [] # Stores messages for OpenAI API
        self.message_queue = queue.Queue() # For thread-safe GUI updates

        # --- GUI Elements ---
        # Conversation display area
        self.text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state='disabled', font=("Arial", 10))
        self.text_area.pack(padx=10, pady=10, expand=True, fill='both')

        # Input frame
        input_frame = tk.Frame(root)
        input_frame.pack(fill='x', padx=10, pady=(0, 10))

        # User input field
        self.input_entry = tk.Entry(input_frame, font=("Arial", 11))
        self.input_entry.pack(side=tk.LEFT, expand=True, fill='x', ipady=5)
        self.input_entry.bind("<Return>", self.send_message_event) # Bind Enter key

        # Send button
        self.send_button = tk.Button(input_frame, text="Send", command=self.send_message_event, width=10)
        self.send_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Initial Setup ---
        self.add_message_to_display("System", "Chat with the Agent (using OpenAI). Use tools like read_file, list_files, edit_file.")
        self.add_message_to_display("System", f"Working directory: {Path.cwd()}")
        # Add initial system prompt if desired (can help guide the model)
        # self.conversation_history.append({"role": "system", "content": "You are a helpful coding assistant agent..."})

        # Start checking the queue for messages from the worker thread
        self.root.after(100, self.process_message_queue)

    def process_message_queue(self):
        """Processes messages from the worker thread to update the GUI safely."""
        try:
            while True:
                role, content, tag = self.message_queue.get_nowait()
                self._add_message_to_display_internal(role, content, tag)
        except queue.Empty:
            pass
        finally:
            # Reschedule itself
            self.root.after(100, self.process_message_queue)

    def add_message_to_display(self, role, content, tag=None):
        """Adds a message to the queue for thread-safe GUI update."""
        # Put the message into the queue instead of directly updating the GUI
        self.message_queue.put((role, content, tag))

    def _add_message_to_display_internal(self, role, content, tag=None):
        """Internal method to update the text area (called by process_message_queue)."""
        self.text_area.config(state='normal')
        if tag:
            self.text_area.insert(tk.END, f"{role}: ", (role, tag))
            self.text_area.insert(tk.END, f"{content}\n", (tag,))
        else:
            self.text_area.insert(tk.END, f"{role}: ", (role,))
            self.text_area.insert(tk.END, f"{content}\n")

        # Configure tags for colors (similar to the Go example)
        self.text_area.tag_config("You", foreground="#0000FF") # Blue
        self.text_area.tag_config("Agent", foreground="#B8860B") # DarkGoldenrod (like Claude's yellow)
        self.text_area.tag_config("Tool", foreground="#008000", font=("Arial", 9, "italic")) # Green, italic
        self.text_area.tag_config("ToolResult", foreground="#555555", font=("Arial", 9)) # Gray
        self.text_area.tag_config("System", foreground="#666666", font=("Arial", 9, "italic")) # Dark Gray
        self.text_area.tag_config("Error", foreground="#FF0000", font=("Arial", 10, "bold")) # Red, bold

        self.text_area.see(tk.END) # Scroll to the bottom
        self.text_area.config(state='disabled')

    def send_message_event(self, event=None):
        """Handles the send button click or Enter key press."""
        user_input = self.input_entry.get().strip()
        if not user_input:
            return # Ignore empty input

        self.add_message_to_display("You", user_input)
        self.conversation_history.append({"role": "user", "content": user_input})
        self.input_entry.delete(0, tk.END) # Clear input field

        # Disable input/button while processing
        self.input_entry.config(state='disabled')
        self.send_button.config(state='disabled')

        # Start API call in a separate thread to avoid blocking GUI
        thread = threading.Thread(target=self.run_inference_thread, daemon=True)
        thread.start()

    def run_inference_thread(self):
        """Runs the OpenAI API call and tool execution logic in a background thread."""
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-2025-04-14",
                messages=self.conversation_history,
                tools=tools_openai_format,
                tool_choice="auto",  # Let the model decide when to use tools
                max_tokens=32768 # Adjust as needed
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls # Check if the model wants to call tools

            # Step 1: Append the Assistant's response (even if it includes tool calls)
            # We store the *entire* message object including potential tool_calls
            # This is important for the API context in the next turn.
            self.conversation_history.append(response_message)

            if tool_calls:
                 # Step 2: Handle Tool Calls
                 self.add_message_to_display("Agent", "Okay, I need to use some tools...") # Let user know

                 # Step 3: Execute tools and gather results
                 tool_messages_for_next_call = [] # Store tool results for the *next* API call
                 for tool_call in tool_calls:
                     function_name = tool_call.function.name
                     function_args_json = tool_call.function.arguments
                     tool_call_id = tool_call.id # Important!

                     # Display the tool call in the GUI
                     self.add_message_to_display("Tool", f"Calling: {function_name}({function_args_json})", tag="Tool")

                     # Find the function
                     function_to_call = available_tools.get(function_name)

                     if function_to_call:
                         try:
                             # Parse arguments (handle potential JSON errors)
                             function_args = json.loads(function_args_json)
                             # Call the actual tool function
                             function_response = function_to_call(**function_args)
                         except json.JSONDecodeError:
                             function_response = f"Error: Invalid JSON arguments received for {function_name}: {function_args_json}"
                             self.add_message_to_display("Error", function_response, tag="Error")
                         except TypeError as e:
                             # Handles wrong arguments passed to the function
                             function_response = f"Error: Invalid arguments for tool {function_name}: {e}. Args received: {function_args_json}"
                             self.add_message_to_display("Error", function_response, tag="Error")
                         except Exception as e:
                             function_response = f"Error executing tool {function_name}: {str(e)}"
                             self.add_message_to_display("Error", function_response, tag="Error")
                     else:
                         function_response = f"Error: Tool '{function_name}' not found."
                         self.add_message_to_display("Error", function_response, tag="Error")

                     # Display the tool result
                     # Limit display length for very long results (like file content)
                     display_response = function_response
                     max_display_len = 500
                     if len(display_response) > max_display_len:
                        display_response = display_response[:max_display_len] + " [... result truncated ...]"
                     self.add_message_to_display("ToolResult", f"Result: {display_response}", tag="ToolResult")

                     # Append the tool result message for the next API call
                     tool_messages_for_next_call.append({
                         "tool_call_id": tool_call_id,
                         "role": "tool",
                         "name": function_name,
                         "content": function_response, # Send the *full* response back to the model
                     })

                 # Step 4: Append all tool results to history
                 self.conversation_history.extend(tool_messages_for_next_call)

                 # Step 5: Call the API *again* with the tool results
                 # Use recursion or just call the method again
                 self.run_inference_thread() # Let the model process the tool results

            else:
                # Step 2 (No Tool Calls): Just display the assistant's text response
                assistant_response = response_message.content
                if assistant_response:
                    self.add_message_to_display("Agent", assistant_response)
                else:
                    # Handle cases where the model might return no text content (e.g., only tool calls were expected but none happened)
                    self.add_message_to_display("System", "[Model returned no text content]", tag="System")


                # Re-enable input after processing is complete
                self.input_entry.config(state='normal')
                self.send_button.config(state='normal')
                self.input_entry.focus() # Put cursor back in input


        except (APIError, RateLimitError) as e:
            error_message = f"OpenAI API Error: {e}"
            self.add_message_to_display("Error", error_message, tag="Error")
            messagebox.showerror("API Error", error_message)
             # Re-enable input on API error
            self.input_entry.config(state='normal')
            self.send_button.config(state='normal')
        except Exception as e:
            error_message = f"An unexpected error occurred: {str(e)}"
            self.add_message_to_display("Error", error_message, tag="Error")
            messagebox.showerror("Error", error_message)
             # Re-enable input on general error
            self.input_entry.config(state='normal')
            self.send_button.config(state='normal')


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = CodeAgentApp(root)
    root.mainloop()
