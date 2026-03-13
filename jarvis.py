import datetime
import os
import sys
import webbrowser
import subprocess
import platform
import random
from typing import Optional


def greet() -> str:
    """Return a greeting based on the current time of day."""
    hour: int = datetime.datetime.now().hour
    if 0 <= hour < 12:
        return "Good Morning! I am Jarvis. How can I assist you?"
    elif 12 <= hour < 17:
        return "Good Afternoon! I am Jarvis. How can I assist you?"
    else:
        return "Good Evening! I am Jarvis. How can I assist you?"


def get_time() -> str:
    """Return the current time as a formatted string."""
    now: datetime.datetime = datetime.datetime.now()
    return f"The current time is {now.strftime('%I:%M %p')}."


def get_date() -> str:
    """Return today's date as a formatted string."""
    today: datetime.date = datetime.date.today()
    return f"Today's date is {today.strftime('%A, %B %d, %Y')}."


def open_website(url: str) -> str:
    """Open a website in the default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opening {url}..."


def tell_joke() -> str:
    """Return a random joke."""
    jokes: list[str] = [
        "Why do programmers prefer dark mode? Because light attracts bugs!",
        "Why did the computer go to the doctor? Because it had a virus!",
        "What do you call a computer that sings? A Dell!",
        "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
        "How many programmers does it take to change a light bulb? None — it's a hardware problem.",
    ]
    return random.choice(jokes)


def get_system_info() -> str:
    """Return basic system information."""
    info: str = (
        f"OS       : {platform.system()} {platform.release()}\n"
        f"Machine  : {platform.machine()}\n"
        f"Processor: {platform.processor()}\n"
        f"Python   : {platform.python_version()}"
    )
    return info


def open_application(app_name: str) -> str:
    """Attempt to open an application by name."""
    system: str = platform.system()
    try:
        if system == "Windows":
            os.startfile(app_name)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen([app_name])
        return f"Opening {app_name}..."
    except Exception as e:
        return f"Sorry, I couldn't open {app_name}. Error: {e}"


def process_command(command: str) -> Optional[str]:
    """
    Parse and process a user command.

    Returns a response string, or None to signal exit.
    """
    command = command.lower().strip()

    if not command:
        return "Please say something."

    # Exit
    if any(word in command for word in ["exit", "quit", "bye", "goodbye"]):
        print("Jarvis: Goodbye! Have a great day.")
        return None

    # Time / Date
    if "time" in command:
        return get_time()
    if "date" in command:
        return get_date()

    # Joke
    if "joke" in command:
        return tell_joke()

    # System info
    if "system" in command or "system info" in command:
        return get_system_info()

    # Open website
    if "open website" in command or "go to" in command:
        parts: list[str] = command.split()
        url: str = parts[-1]
        return open_website(url)

    # Open YouTube / Google shortcuts
    if "youtube" in command:
        return open_website("https://www.youtube.com")
    if "google" in command:
        return open_website("https://www.google.com")
    if "github" in command:
        return open_website("https://www.github.com")

    # Open app
    if "open" in command:
        app: str = command.replace("open", "").strip()
        return open_application(app)

    # Help
    if "help" in command:
        return (
            "Here's what I can do:\n"
            "  • Tell you the current time        → 'time'\n"
            "  • Tell you today's date            → 'date'\n"
            "  • Tell a joke                      → 'joke'\n"
            "  • Show system info                 → 'system info'\n"
            "  • Open a website                   → 'open website <url>'\n"
            "  • Open YouTube / Google / GitHub   → 'youtube', 'google', 'github'\n"
            "  • Open an application              → 'open <app name>'\n"
            "  • Exit                             → 'exit' or 'bye'"
        )

    return f"Sorry, I don't understand '{command}' yet. Type 'help' to see what I can do."


def main() -> None:
    """Main entry point — run the Jarvis REPL."""
    print(f"Jarvis: {greet()}")
    print("Jarvis: Type 'help' to see available commands.\n")

    while True:
        try:
            user_input: str = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nJarvis: Goodbye!")
            sys.exit(0)

        response: Optional[str] = process_command(user_input)

        if response is None:
            sys.exit(0)

        print(f"Jarvis: {response}\n")


if __name__ == "__main__":
    main()
