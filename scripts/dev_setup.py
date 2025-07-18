#!/usr/bin/env python3
"""Development setup script for TA2 App."""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: str, description: str) -> bool:
    """Run a command and return success status."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"Command: {cmd}")
        print(f"Error: {e.stderr}")
        return False


def main():
    """Main setup function."""
    print("🚀 Setting up TA2 App development environment...")
    
    # Check if we're in a Poetry project
    if not Path("pyproject.toml").exists():
        print("❌ No pyproject.toml found. Please run this script from the project root.")
        sys.exit(1)
    
    # Install dependencies
    if not run_command("poetry install", "Installing dependencies"):
        sys.exit(1)
    
    # Install pre-commit hooks
    if not run_command("poetry run pre-commit install", "Installing pre-commit hooks"):
        sys.exit(1)
    
    # Run initial code quality checks
    if not run_command("poetry run ruff check ta2_app", "Running linter checks"):
        print("⚠️  Linter found issues. Run 'poetry run ruff check --fix ta2_app' to fix.")
    
    # Run type checking
    if not run_command("poetry run mypy ta2_app", "Running type checker"):
        print("⚠️  Type checker found issues. Please review and fix.")
    
    # Run tests
    if not run_command("poetry run pytest", "Running test suite"):
        print("⚠️  Some tests failed. Please review and fix.")
    
    print("\n🎉 Development environment setup complete!")
    print("\nNext steps:")
    print("1. Review any warnings above")
    print("2. Start developing with: poetry shell")
    print("3. Run tests with: poetry run pytest")
    print("4. Format code with: poetry run ruff format")


if __name__ == "__main__":
    main()