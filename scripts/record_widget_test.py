#!/usr/bin/env python3
"""
Record widget test scenarios by capturing debug messages from guidance executions.

Usage:
    python record_widget_test.py --name "role_assignment" --output tests/fixtures/
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import guidance


def record_scenario(name: str, scenario_func, output_dir: str = "tests/fixtures"):
    """
    Record a test scenario by running guidance code and capturing widget messages.
    
    Args:
        name: Name for the test scenario
        scenario_func: Function that runs the guidance code
        output_dir: Directory to save the recording
    """
    # Enable widget debug mode
    guidance.enable_widget_debug()
    guidance.clear_widget_debug()
    
    print(f"Recording scenario: {name}")
    print("=" * 50)
    
    # Run the scenario
    try:
        result = scenario_func()
        print(f"Scenario completed successfully")
        if result:
            print(f"Result: {result}")
    except Exception as e:
        print(f"Error during scenario execution: {e}")
        raise
    
    # Capture debug data
    debug_data = guidance.dump_widget_debug()
    
    if not debug_data:
        print("Warning: No debug data captured. Make sure you're using a Jupyter environment.")
        return None
    
    # Parse and enhance the debug data
    recording = json.loads(debug_data)
    recording['scenario_name'] = name
    recording['recorded_at'] = datetime.now().isoformat()
    
    # Save to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = output_path / filename
    
    with open(filepath, 'w') as f:
        json.dump(recording, f, indent=2)
    
    print(f"\nRecording saved to: {filepath}")
    print(f"Total messages: {recording['messageCount']}")
    
    # Print summary
    message_types = {}
    for msg in recording['messages']:
        msg_type = msg['class_name']
        message_types[msg_type] = message_types.get(msg_type, 0) + 1
    
    print("\nMessage type summary:")
    for msg_type, count in sorted(message_types.items()):
        print(f"  {msg_type}: {count}")
    
    return filepath


# Example scenarios

def basic_conversation_scenario():
    """Basic user-assistant conversation with roles."""
    from guidance import models, system, user, assistant, gen
    
    gpt35 = models.OpenAI("gpt-3.5-turbo")
    
    with system():
        lm = gpt35 + "You are a helpful assistant."
    
    with user():
        lm += "What is 2+2?"
    
    with assistant():
        lm += gen("response", max_tokens=10)
    
    return lm


def multi_turn_conversation_scenario():
    """Multi-turn conversation to test role switching."""
    from guidance import models, system, user, assistant, gen
    
    gpt35 = models.OpenAI("gpt-3.5-turbo")
    
    with system():
        lm = gpt35 + "You are a helpful math tutor."
    
    with user():
        lm += "What is the meaning of life?"
    
    with assistant():
        lm += gen("response1", max_tokens=5)
    
    with user():
        lm += "Why?"
    
    with assistant():
        lm += gen("response2", max_tokens=5)
    
    with user():
        lm += "Are you sure?"
    
    with assistant():
        lm += gen("response3", max_tokens=5)
    
    return lm


def backtracking_scenario():
    """Scenario with backtracking/correction."""
    from guidance import models, select, assistant
    
    gpt35 = models.OpenAI("gpt-3.5-turbo")
    
    with assistant():
        lm = gpt35 + "The answer is " + select(["yes", "no", "maybe"])
    
    return lm


def complex_formatting_scenario():
    """Complex scenario with multiple formatting elements."""
    from guidance import models, system, user, assistant, gen, select
    
    gpt35 = models.OpenAI("gpt-3.5-turbo")
    
    with system():
        lm = gpt35 + "You are a helpful assistant that provides structured responses."
    
    with user():
        lm += "Give me a recipe for chocolate cake."
    
    with assistant():
        lm += "Here's a simple chocolate cake recipe:\n\n"
        lm += "**Ingredients:**\n"
        lm += "- " + gen("ingredient1", max_tokens=10) + "\n"
        lm += "- " + gen("ingredient2", max_tokens=10) + "\n"
        lm += "- " + gen("ingredient3", max_tokens=10) + "\n"
        lm += "\n**Instructions:**\n"
        lm += "1. " + gen("step1", max_tokens=20) + "\n"
        lm += "2. " + gen("step2", max_tokens=20) + "\n"
    
    return lm


# Scenario registry
SCENARIOS = {
    'basic': basic_conversation_scenario,
    'multi_turn': multi_turn_conversation_scenario,
    'backtracking': backtracking_scenario,
    'complex': complex_formatting_scenario,
}


def main():
    parser = argparse.ArgumentParser(description='Record widget test scenarios')
    parser.add_argument('--name', '-n', required=True, 
                       help='Name for the test scenario')
    parser.add_argument('--scenario', '-s', choices=list(SCENARIOS.keys()),
                       help='Predefined scenario to run')
    parser.add_argument('--output', '-o', default='tests/fixtures',
                       help='Output directory for recordings')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available scenarios')
    
    args = parser.parse_args()
    
    if args.list:
        print("Available scenarios:")
        for name, func in SCENARIOS.items():
            print(f"  {name}: {func.__doc__}")
        return
    
    if args.scenario:
        scenario_func = SCENARIOS[args.scenario]
        record_scenario(args.name, scenario_func, args.output)
    else:
        print("Error: Please specify a --scenario to run")
        print("Use --list to see available scenarios")
        return 1


if __name__ == '__main__':
    main()