"""Main of the terminal container: starts the editor (VS Code in the browser) and the terminal service.
Also `python -m editor_launcher claude ...`, which the Verdict extension runs in a VS Code terminal."""

from terminal.editor import main

if __name__ == "__main__":
    main()
