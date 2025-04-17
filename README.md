# OpenAI Coding Agent in Python

<img src="https://github.com/alby13/OpenAI-Coding-Agent-in-Python/blob/main/coding-agent-screenshot.jpg">

## Overview

OpenAI Coding Agent in Python is a Python application with a graphical interface (Tkinter) for working with files and directories in your project, with tools tailored for integration with the OpenAI API. It enables you to read, list, and edit files securely from a user-friendly GUI, and handles OpenAI API key management for you.

This program is inspired by Thorsten Ball's "How to Build an Agent" https://ampcode.com/how-to-build-an-agent

## Features

- **OpenAI API key management** (from `.env` or user prompt)
- **Read file contents** in the project directory
- **List files and folders** (with directory traversal prevention)
- **Edit or create files** with controlled string replacement
- **Robust error handling** and user feedback (GUI popups)
- **Integration-ready:** Tool definitions are accessible for LLM agents

## Requirements

- Python 3.8+
- `openai` Python package
- `tkinter` (usually included with Python)
- `python-dotenv`

Install needed dependencies with:
```
pip install openai python-dotenv
```

## Usage

1. Ensure you have your OpenAI API key set as an environment variable (`OPENAI_API_KEY`) or in a `.env` file in the project directory.
2. Run the application:
   ```
   python main_gui.py
   ```
3. The program will prompt you for an API key if needed.
4. Use the GUI to:
    - Read files
    - List directory contents
    - Edit files by replacing all instances of a string
    - Create new files

## Safe & Secure

- For safety, the utility only allows file operations within your project directory.
- Attempts to access or edit files outside this directory are blocked.

## Developer Notes

- The tool functions (`read_file`, `list_files`, `edit_file`) are defined both for GUI use and for potential integration with LLM agents or API.
- Functions use JSON and direct file reads/writes for easy extensibility.
- Error reporting is user-friendly via dialogs.

## License

MIT License
