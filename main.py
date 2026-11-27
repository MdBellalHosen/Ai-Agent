"""Run the assistant:  python main.py          (chat)
                       python main.py --check  (test the setup)
"""
import sys

if __name__ == "__main__":
    if "--check" in sys.argv:
        from agent.check import run
        sys.exit(run(offline="--offline" in sys.argv))
    from agent.cli import main
    main()
