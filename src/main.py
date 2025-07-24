# main.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.agent import Agent

def main():
    # Initialize the agent
    agent = Agent()

    # Run the summarization process and output the result
    result = agent.run()
    print(result)
    
    # Save to markdown file for proper formatting
    with open("work_item_summaries.md", "w", encoding="utf-8") as f:
        f.write(result)
    print(f"\nSummaries saved to: work_item_summaries.md")
    
    # Exit with success if non-empty
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()