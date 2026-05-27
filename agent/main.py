import asyncio
import sys

from dotenv import load_dotenv

from agent.loop import run


def main() -> None:
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python -m agent.main \"<research question>\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"\n[Sift] Research question: {question}\n")

    asyncio.run(run(question))


if __name__ == "__main__":
    main()
