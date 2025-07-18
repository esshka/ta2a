#!/usr/bin/env python3
"""
Run All Examples - TA2 Breakout Evaluation Engine

This script runs all available examples in sequence, providing a comprehensive
demonstration of the TA2 system capabilities. It includes timing, error handling,
and summary reporting.

Run: python examples/run_all_examples.py
"""

import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List
import importlib.util


class ExampleRunner:
    """Manages execution of all example scripts."""
    
    def __init__(self):
        self.results = []
        self.start_time = None
        self.examples_dir = Path(__file__).parent
        
    def run_example(self, example_name: str, module_path: Path) -> Dict[str, Any]:
        """Run a single example script and capture results."""
        print(f"\n{'='*60}")
        print(f"🚀 RUNNING: {example_name}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        try:
            # Import and run the example module
            spec = importlib.util.spec_from_file_location(example_name, module_path)
            module = importlib.util.module_from_spec(spec)
            
            # Capture stdout for analysis
            original_stdout = sys.stdout
            from io import StringIO
            captured_output = StringIO()
            
            try:
                sys.stdout = captured_output
                spec.loader.exec_module(module)
                
                # Run main function if it exists
                if hasattr(module, 'main'):
                    module.main()
                
            finally:
                sys.stdout = original_stdout
                
            output = captured_output.getvalue()
            
            # Restore stdout and print the output
            print(output)
            
            duration = time.time() - start_time
            
            return {
                'name': example_name,
                'status': 'success',
                'duration': duration,
                'output_length': len(output),
                'error': None
            }
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {e}"
            
            print(f"❌ ERROR in {example_name}: {error_msg}")
            print(f"Traceback:")
            traceback.print_exc()
            
            return {
                'name': example_name,
                'status': 'failed',
                'duration': duration,
                'output_length': 0,
                'error': error_msg
            }
    
    def run_all_examples(self):
        """Run all available examples."""
        print("🎯 TA2 COMPREHENSIVE EXAMPLE SUITE")
        print("=" * 60)
        print("Running all available examples to demonstrate TA2 capabilities...")
        print()
        
        self.start_time = time.time()
        
        # Define examples in order of complexity
        examples = [
            {
                'name': 'Data Ingestion Demo',
                'file': 'data_ingestion_demo.py',
                'description': 'Data parsing, validation, and spike filtering'
            },
            {
                'name': 'Configuration Demo',
                'file': 'configuration_demo.py',
                'description': 'Configuration system and parameter management'
            },
            {
                'name': 'Basic Usage',
                'file': 'basic_usage.py',
                'description': 'Basic engine usage and signal generation'
            },
            {
                'name': 'State Machine Demo',
                'file': 'state_machine_demo.py',
                'description': 'State transitions and breakout lifecycle'
            }
        ]
        
        print(f"📋 EXAMPLE SCHEDULE:")
        for i, example in enumerate(examples, 1):
            print(f"  {i}. {example['name']}")
            print(f"     File: {example['file']}")
            print(f"     Focus: {example['description']}")
        print()
        
        # Run each example
        for i, example in enumerate(examples, 1):
            print(f"\n🔄 Example {i}/{len(examples)}: {example['name']}")
            
            module_path = self.examples_dir / example['file']
            if not module_path.exists():
                print(f"❌ File not found: {module_path}")
                result = {
                    'name': example['name'],
                    'status': 'not_found',
                    'duration': 0,
                    'output_length': 0,
                    'error': f"File not found: {example['file']}"
                }
            else:
                result = self.run_example(example['name'], module_path)
            
            self.results.append(result)
            
            # Show progress
            success_count = sum(1 for r in self.results if r['status'] == 'success')
            print(f"\n📊 Progress: {success_count}/{len(self.results)} examples completed successfully")
        
        # Generate summary
        self.print_summary()
    
    def print_summary(self):
        """Print comprehensive summary of all examples."""
        total_duration = time.time() - self.start_time
        
        print(f"\n{'='*60}")
        print(f"📊 COMPREHENSIVE EXAMPLE SUMMARY")
        print(f"{'='*60}")
        
        # Overall stats
        total_examples = len(self.results)
        successful = sum(1 for r in self.results if r['status'] == 'success')
        failed = sum(1 for r in self.results if r['status'] == 'failed')
        not_found = sum(1 for r in self.results if r['status'] == 'not_found')
        
        print(f"📈 Overall Results:")
        print(f"  Total examples: {total_examples}")
        print(f"  Successful: {successful} ✅")
        print(f"  Failed: {failed} ❌")
        print(f"  Not found: {not_found} ❓")
        print(f"  Success rate: {(successful/total_examples)*100:.1f}%")
        print(f"  Total duration: {total_duration:.2f}s")
        
        # Individual results
        print(f"\n📋 Individual Results:")
        for i, result in enumerate(self.results, 1):
            status_icon = {
                'success': '✅',
                'failed': '❌',
                'not_found': '❓'
            }.get(result['status'], '❓')
            
            print(f"  {i}. {result['name']}: {status_icon} {result['status']}")
            print(f"     Duration: {result['duration']:.2f}s")
            print(f"     Output: {result['output_length']:,} chars")
            if result['error']:
                print(f"     Error: {result['error']}")
        
        # Performance analysis
        if successful > 0:
            successful_results = [r for r in self.results if r['status'] == 'success']
            avg_duration = sum(r['duration'] for r in successful_results) / len(successful_results)
            max_duration = max(r['duration'] for r in successful_results)
            min_duration = min(r['duration'] for r in successful_results)
            
            print(f"\n⚡ Performance Analysis:")
            print(f"  Average duration: {avg_duration:.2f}s")
            print(f"  Fastest example: {min_duration:.2f}s")
            print(f"  Slowest example: {max_duration:.2f}s")
            print(f"  Total output: {sum(r['output_length'] for r in successful_results):,} chars")
        
        # Recommendations
        print(f"\n💡 Next Steps:")
        if successful == total_examples:
            print("  🎉 All examples completed successfully!")
            print("  ✅ The TA2 system is working correctly")
            print("  📚 Review the output above to understand each capability")
            print("  🔧 Try modifying the examples to test your specific use cases")
            print("  🚀 Consider integrating with real exchange data feeds")
        else:
            print("  ⚠️ Some examples failed - review the errors above")
            print("  🔍 Check system requirements and dependencies")
            print("  📖 Consult the documentation for troubleshooting")
            print("  🧪 Try running individual examples to isolate issues")
        
        print(f"\n📖 Documentation:")
        print(f"  Main README: ../README.md")
        print(f"  Implementation spec: ../dev_proto.md")
        print(f"  Configuration guide: ../config/")
        print(f"  Test suite: ../tests/")
        
        print(f"\n🏁 Example suite completed in {total_duration:.2f}s")


def main():
    """Main function to run all examples."""
    try:
        runner = ExampleRunner()
        runner.run_all_examples()
    except KeyboardInterrupt:
        print(f"\n\n⏹️ Example suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error in example runner: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()