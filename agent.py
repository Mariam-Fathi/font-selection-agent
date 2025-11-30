"""Root Agent - Font Selection Agent MVP"""

import os
from dotenv import load_dotenv
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from agents.font_agent import font_selection_agent

# Load environment variables
load_dotenv()

# Create session service
session_service = InMemorySessionService()

# Create the runner with the font selection agent
runner = Runner(
    app_name="font-selection-agent",
    agent=font_selection_agent,
    session_service=session_service,
)

if __name__ == "__main__":
    import asyncio
    
    # Run the agent interactively
    print("Font Selection Agent")
    print("=" * 50)
    print("\nI can help you find the perfect font for your design!")
    print("\nI'll ask you for:")
    print("  1. The path to your HTML file (e.g., 'test-design.html')")
    print("  2. Then I'll show you font category options to choose from")
    print("\nThen I'll search for fonts and take screenshots automatically!")
    print("\nExample:")
    print('  You: "I want to test fonts"')
    print('  Agent: "What is the path to your HTML file?"')
    print('  You: "test-design.html"')
    print('  Agent: "Choose a category: 1. Handwriting, 2. Serif, 3. Sans-serif..."')
    print('  You: "1"')
    print("\n" + "=" * 50 + "\n")
    
    async def run_interactive():
        # Run the agent interactively
        while True:
            try:
                user_input = input("You: ")
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                # Use run_debug for simple interactive testing
                print()  # Add a blank line
                await runner.run_debug(user_input)
                print()  # Add a blank line after response
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")
    
    # Run the async function
    asyncio.run(run_interactive())

