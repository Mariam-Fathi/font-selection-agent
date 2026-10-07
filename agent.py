"""Root Agent - Font Selection Agent MVP"""

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
    print("=" * 50 + "\n")
    
    async def run_interactive():
        # Start with first question
        print("What is the path to your UI file?")
        print()
        
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
                error_msg = str(e)
                if "503" in error_msg or "overloaded" in error_msg.lower():
                    print("\n⚠️  The API is temporarily overloaded. Please try again in a moment.\n")
                elif "API key" in error_msg or "authentication" in error_msg.lower():
                    print("\n⚠️  API key error. Please check your .env file and GOOGLE_API_KEY.\n")
                else:
                    print(f"\n⚠️  Error: {error_msg}\n")
    
    # Run the async function
    asyncio.run(run_interactive())

