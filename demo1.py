"""
Demo 1: graphical Python academic scheduling system.
Author: Sunny Zou
Date: 2026-11-13
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Academic Task Planner - course version")
    parser.add_argument("--data", help="Path to the course-version JSON file")
    args = parser.parse_args()
    from course_demo.ui import run
    return run(args.data)


if __name__ == "__main__":
    raise SystemExit(main())
