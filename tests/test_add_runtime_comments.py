import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from codeflash.code_utils.edit_generated_tests import add_runtime_comments_to_generated_tests
from codeflash.models.models import GeneratedTests, GeneratedTestsList, InvocationId, FunctionTestInvocation, TestType, \
    VerificationType, TestResults
from codeflash.verification.verification_utils import TestConfig

@pytest.fixture
def test_config():
    """Create a mock TestConfig for testing."""
    config = Mock(spec=TestConfig)
    config.project_root_path = Path("/project")
    config.test_framework= "pytest"
    config.tests_project_rootdir = Path("/project/tests")
    config.tests_root = Path("/project/tests")
    return config

class TestAddRuntimeComments:
    """Test cases for add_runtime_comments_to_generated_tests method."""

    def create_test_invocation(
        self, test_function_name: str, runtime: int, loop_index: int = 1, iteration_id: str = "1", did_pass: bool = True
    ) -> FunctionTestInvocation:
        """Helper to create test invocation objects."""
        return FunctionTestInvocation(
            loop_index=loop_index,
            id=InvocationId(
                test_module_path="tests.test_module",
                test_class_name=None,
                test_function_name=test_function_name,
                function_getting_tested="test_function",
                iteration_id=iteration_id,
            ),
            file_name=Path("tests/test.py"),
            did_pass=did_pass,
            runtime=runtime,
            test_framework="pytest",
            test_type=TestType.GENERATED_REGRESSION,
            return_value=None,
            timed_out=False,
            verification_type=VerificationType.FUNCTION_CALL,
        )

    def test_basic_runtime_comment_addition(self, test_config):
        """Test basic functionality of adding runtime comments."""
        # Create test source code
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )
        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        # Add test invocations with different runtimes
        original_invocation = self.create_test_invocation("test_bubble_sort", 500_000, iteration_id='0')  # 500μs
        optimized_invocation = self.create_test_invocation("test_bubble_sort", 300_000, iteration_id='0')  # 300μs

        original_test_results.add(original_invocation)
        optimized_test_results.add(optimized_invocation)
        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()
        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that comments were added
        modified_source = result.generated_tests[0].generated_original_test_source
        assert "# 500μs -> 300μs" in modified_source
        assert "codeflash_output = bubble_sort([3, 1, 2]) # 500μs -> 300μs" in modified_source

    def test_multiple_test_functions(self, test_config):
        """Test handling multiple test functions in the same file."""
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]

def test_quick_sort():
    codeflash_output = quick_sort([5, 2, 8])
    assert codeflash_output == [2, 5, 8]

def helper_function():
    return "not a test"
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results for both functions
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        # Add test invocations for both test functions
        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000, iteration_id='0'))
        original_test_results.add(self.create_test_invocation("test_quick_sort", 800_000, iteration_id='0'))

        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000, iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_quick_sort", 600_000, iteration_id='0'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        modified_source = result.generated_tests[0].generated_original_test_source

        # Check that comments were added to both test functions
        assert "# 500μs -> 300μs" in modified_source
        assert "# 800μs -> 600μs" in modified_source
        # Helper function should not have comments
        assert (
            "helper_function():" in modified_source
            and "# " not in modified_source.split("helper_function():")[1].split("\n")[0]
        )

    def test_different_time_formats(self, test_config):
        """Test that different time ranges are formatted correctly with new precision rules."""
        test_cases = [
            (999, 500, "999ns -> 500ns"),  # nanoseconds
            (25_000, 18_000, "25.0μs -> 18.0μs"),  # microseconds with precision
            (500_000, 300_000, "500μs -> 300μs"),  # microseconds full integers
            (1_500_000, 800_000, "1.50ms -> 800μs"),  # milliseconds with precision
            (365_000_000, 290_000_000, "365ms -> 290ms"),  # milliseconds full integers
            (2_000_000_000, 1_500_000_000, "2.00s -> 1.50s"),  # seconds with precision
        ]

        for original_time, optimized_time, expected_comment in test_cases:
            test_source = """def test_function():
    #this comment will be removed in ast form
    codeflash_output = some_function()
    assert codeflash_output is not None
"""

            generated_test = GeneratedTests(
                generated_original_test_source=test_source,
                instrumented_behavior_test_source="",
                instrumented_perf_test_source="",
                behavior_file_path=Path("/project/tests/test_module.py"),
                perf_file_path=Path("/project/tests/test_module_perf.py")
            )

            generated_tests = GeneratedTestsList(generated_tests=[generated_test])

            # Create test results
            original_test_results = TestResults()
            optimized_test_results = TestResults()

            original_test_results.add(self.create_test_invocation("test_function", original_time, iteration_id='0'))
            optimized_test_results.add(self.create_test_invocation("test_function", optimized_time, iteration_id='0'))

            original_runtimes = original_test_results.usable_runtime_data_by_test_case()
            optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()
            # Test the functionality
            result = add_runtime_comments_to_generated_tests(
                test_config, generated_tests, original_runtimes, optimized_runtimes
            )

            modified_source = result.generated_tests[0].generated_original_test_source
            assert f"# {expected_comment}" in modified_source

    def test_missing_test_results(self, test_config):
        """Test behavior when test results are missing for a test function."""
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create empty test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that no comments were added
        modified_source = result.generated_tests[0].generated_original_test_source
        assert modified_source == test_source  # Should be unchanged

    def test_partial_test_results(self, test_config):
        """Test behavior when only one set of test results is available."""
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results with only original data
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000, iteration_id='0'))
        # No optimized results
        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()
        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that no comments were added
        modified_source = result.generated_tests[0].generated_original_test_source
        assert modified_source == test_source  # Should be unchanged

    def test_multiple_runtimes_uses_minimum(self, test_config):
        """Test that when multiple runtimes exist, the minimum is used."""
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results with multiple loop iterations
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        # Add multiple runs with different runtimes
        original_test_results.add(self.create_test_invocation("test_bubble_sort", 600_000, loop_index=1,iteration_id='0'))
        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000, loop_index=2,iteration_id='0'))
        original_test_results.add(self.create_test_invocation("test_bubble_sort", 550_000, loop_index=3,iteration_id='0'))

        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 350_000, loop_index=1,iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000, loop_index=2,iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 320_000, loop_index=3,iteration_id='0'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()
        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that minimum times were used (500μs -> 300μs)
        modified_source = result.generated_tests[0].generated_original_test_source
        assert "# 500μs -> 300μs" in modified_source

    def test_no_codeflash_output_assignment(self, test_config):
        """Test behavior when test doesn't have codeflash_output assignment."""
        test_source = """def test_bubble_sort():
    result = bubble_sort([3, 1, 2])
    assert result == [1, 2, 3]
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000,iteration_id='-1'))
        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000,iteration_id='-1'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that no comments were added (no codeflash_output assignment)
        modified_source = result.generated_tests[0].generated_original_test_source
        assert modified_source == test_source  # Should be unchanged

    def test_invalid_python_code_handling(self, test_config):
        """Test behavior when test source code is invalid Python."""
        test_source = """def test_bubble_sort(:
        codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""  # Invalid syntax: extra indentation

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000,iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000,iteration_id='0'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality - should handle parse error gracefully
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that original test is preserved when parsing fails
        modified_source = result.generated_tests[0].generated_original_test_source
        assert modified_source == test_source  # Should be unchanged due to parse error

    def test_multiple_generated_tests(self, test_config):
        """Test handling multiple generated test objects."""
        test_source_1 = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        test_source_2 = """def test_quick_sort():
    a=1
    b=2
    c=3
    codeflash_output = quick_sort([5, 2, 8])
    assert codeflash_output == [2, 5, 8]
"""

        generated_test_1 = GeneratedTests(
            generated_original_test_source=test_source_1,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_test_2 = GeneratedTests(
            generated_original_test_source=test_source_2,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test_1, generated_test_2])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000,iteration_id='0'))
        original_test_results.add(self.create_test_invocation("test_quick_sort", 800_000,iteration_id='3'))

        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000,iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_quick_sort", 600_000,iteration_id='3'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that comments were added to both test files
        modified_source_1 = result.generated_tests[0].generated_original_test_source
        modified_source_2 = result.generated_tests[1].generated_original_test_source

        assert "# 500μs -> 300μs" in modified_source_1
        assert "# 800μs -> 600μs" in modified_source_2

    def test_preserved_test_attributes(self, test_config):
        """Test that other test attributes are preserved during modification."""
        test_source = """def test_bubble_sort():
    codeflash_output = bubble_sort([3, 1, 2])
    assert codeflash_output == [1, 2, 3]
"""

        original_behavior_source = "behavior test source"
        original_perf_source = "perf test source"
        original_behavior_path = Path("/project/tests/test_module.py")
        original_perf_path = Path("/project/tests/test_module_perf.py")

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source=original_behavior_source,
            instrumented_perf_test_source=original_perf_source,
            behavior_file_path=original_behavior_path,
            perf_file_path=original_perf_path
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_bubble_sort", 500_000,iteration_id='0'))
        optimized_test_results.add(self.create_test_invocation("test_bubble_sort", 300_000,iteration_id='0'))

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()
        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that other attributes are preserved
        modified_test = result.generated_tests[0]
        assert modified_test.instrumented_behavior_test_source == original_behavior_source
        assert modified_test.instrumented_perf_test_source == original_perf_source
        assert modified_test.behavior_file_path == original_behavior_path
        assert modified_test.perf_file_path == original_perf_path

        # Check that only the generated_original_test_source was modified
        assert "# 500μs -> 300μs" in modified_test.generated_original_test_source

    def test_multistatement_line_handling(self, test_config):
        """Test that runtime comments work correctly with multiple statements on one line."""
        test_source = """def test_mutation_of_input():
    # Test that the input list is mutated in-place and returned
    arr = [3, 1, 2]
    codeflash_output = sorter(arr); result = codeflash_output
    assert result == [1, 2, 3]
    assert arr == [1, 2, 3]  # Input should be mutated
"""

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py")
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Create test results
        original_test_results = TestResults()
        optimized_test_results = TestResults()

        original_test_results.add(self.create_test_invocation("test_mutation_of_input", 19_000,iteration_id='1'))  # 19μs
        optimized_test_results.add(self.create_test_invocation("test_mutation_of_input", 14_000,iteration_id='1'))  # 14μs

        original_runtimes = original_test_results.usable_runtime_data_by_test_case()
        optimized_runtimes = optimized_test_results.usable_runtime_data_by_test_case()

        # Test the functionality
        result = add_runtime_comments_to_generated_tests(test_config, generated_tests, original_runtimes, optimized_runtimes)

        # Check that comments were added to the correct line
        modified_source = result.generated_tests[0].generated_original_test_source
        assert "# 19.0μs -> 14.0μs" in modified_source

        # Verify the comment is on the line with codeflash_output assignment
        lines = modified_source.split("\n")
        codeflash_line = None
        for line in lines:
            if "codeflash_output = sorter(arr)" in line:
                codeflash_line = line
                break

        assert codeflash_line is not None, "Could not find codeflash_output assignment line"
        assert "# 19.0μs -> 14.0μs" in codeflash_line, f"Comment not found in the correct line: {codeflash_line}"


    def test_add_runtime_comments_simple_function(self, test_config):
        """Test adding runtime comments to a simple test function."""
        test_source = '''def test_function():
    codeflash_output = some_function()
    assert codeflash_output == expected
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        invocation_id = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="0",
        )

        original_runtimes = {invocation_id: [1000000000, 1200000000]}  # 1s, 1.2s in nanoseconds
        optimized_runtimes = {invocation_id: [500000000, 600000000]}   # 0.5s, 0.6s in nanoseconds

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        expected_source = '''def test_function():
    codeflash_output = some_function() # 1.00s -> 500ms (100% faster)
    assert codeflash_output == expected
'''

        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == expected_source

    def test_add_runtime_comments_class_method(self, test_config):
        """Test adding runtime comments to a test method within a class."""
        test_source = '''class TestClass:
    def test_function(self):
        codeflash_output = some_function()
        assert codeflash_output == expected
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        invocation_id = InvocationId(
            test_module_path="tests.test_module",
            test_class_name="TestClass",
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="0",

        )

        original_runtimes = {invocation_id: [2000000000]}  # 2s in nanoseconds
        optimized_runtimes = {invocation_id: [1000000000]} # 1s in nanoseconds

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        expected_source = '''class TestClass:
    def test_function(self):
        codeflash_output = some_function() # 2.00s -> 1.00s (100% faster)
        assert codeflash_output == expected
'''

        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == expected_source

    def test_add_runtime_comments_multiple_assignments(self, test_config):
        """Test adding runtime comments when there are multiple codeflash_output assignments."""
        test_source = '''def test_function():
    setup_data = prepare_test()
    codeflash_output = some_function()
    assert codeflash_output == expected
    codeflash_output = another_function()
    assert codeflash_output == expected2
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        invocation_id1 = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="1",
        )
        invocation_id2 = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="another_function",
            iteration_id="3",
        )

        original_runtimes = {invocation_id1: [1500000000], invocation_id2: [10]}  # 1.5s in nanoseconds
        optimized_runtimes = {invocation_id1: [750000000], invocation_id2: [5]}  # 0.75s in nanoseconds

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        expected_source = '''def test_function():
    setup_data = prepare_test()
    codeflash_output = some_function() # 1.50s -> 750ms (100% faster)
    assert codeflash_output == expected
    codeflash_output = another_function() # 10ns -> 5ns (100% faster)
    assert codeflash_output == expected2
'''

        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == expected_source

    def test_add_runtime_comments_no_matching_runtimes(self, test_config):
        """Test that source remains unchanged when no matching runtimes are found."""
        test_source = '''def test_function():
    codeflash_output = some_function()
    assert codeflash_output == expected
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        # Different invocation ID that won't match
        invocation_id = InvocationId(
            test_module_path="tests.other_module",
            test_class_name=None,
            test_function_name="other_function",
            function_getting_tested="some_other_function",
            iteration_id="0",
        )

        original_runtimes = {invocation_id: [1000000000]}
        optimized_runtimes = {invocation_id: [500000000]}

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        # Source should remain unchanged
        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == test_source

    def test_add_runtime_comments_no_codeflash_output(self, test_config):
        """Test that source remains unchanged when there's no codeflash_output assignment."""
        test_source = '''def test_function():
    result = some_function()
    assert result == expected
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        invocation_id = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="0",
        )

        original_runtimes = {invocation_id: [1000000000]}
        optimized_runtimes = {invocation_id: [500000000]}

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        # Source should remain unchanged
        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == test_source

    def test_add_runtime_comments_multiple_tests(self, test_config):
        """Test adding runtime comments to multiple generated tests."""
        test_source1 = '''def test_function1():
    codeflash_output = some_function()
    assert codeflash_output == expected
'''

        test_source2 = '''def test_function2():
    codeflash_output = another_function()
    assert codeflash_output == expected
'''

        generated_test1 = GeneratedTests(
            generated_original_test_source=test_source1,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module1.py"),
            perf_file_path=Path("/project/tests/test_module1_perf.py"),
        )

        generated_test2 = GeneratedTests(
            generated_original_test_source=test_source2,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module2.py"),
            perf_file_path=Path("/project/tests/test_module2_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test1, generated_test2])

        invocation_id1 = InvocationId(
            test_module_path="tests.test_module1",
            test_class_name=None,
            test_function_name="test_function1",
            function_getting_tested="some_function",
            iteration_id="0",
        )

        invocation_id2 = InvocationId(
            test_module_path="tests.test_module2",
            test_class_name=None,
            test_function_name="test_function2",
            function_getting_tested="another_function",
            iteration_id = "0",
        )

        original_runtimes = {
            invocation_id1: [1000000000],  # 1s
            invocation_id2: [2000000000],  # 2s
        }
        optimized_runtimes = {
            invocation_id1: [500000000],   # 0.5s
            invocation_id2: [800000000],   # 0.8s
        }

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        expected_source1 = '''def test_function1():
    codeflash_output = some_function() # 1.00s -> 500ms (100% faster)
    assert codeflash_output == expected
'''

        expected_source2 = '''def test_function2():
    codeflash_output = another_function() # 2.00s -> 800ms (150% faster)
    assert codeflash_output == expected
'''

        assert len(result.generated_tests) == 2
        assert result.generated_tests[0].generated_original_test_source == expected_source1
        assert result.generated_tests[1].generated_original_test_source == expected_source2

    def test_add_runtime_comments_performance_regression(self, test_config):
        """Test adding runtime comments when optimized version is slower (negative performance gain)."""
        test_source = '''def test_function():
    codeflash_output = some_function()
    assert codeflash_output == expected
    codeflash_output = some_function()
    assert codeflash_output == expected
'''

        generated_test = GeneratedTests(
            generated_original_test_source=test_source,
            instrumented_behavior_test_source="",
            instrumented_perf_test_source="",
            behavior_file_path=Path("/project/tests/test_module.py"),
            perf_file_path=Path("/project/tests/test_module_perf.py"),
        )

        generated_tests = GeneratedTestsList(generated_tests=[generated_test])

        invocation_id1 = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="0",
        )

        invocation_id2 = InvocationId(
            test_module_path="tests.test_module",
            test_class_name=None,
            test_function_name="test_function",
            function_getting_tested="some_function",
            iteration_id="2",
        )

        original_runtimes = {invocation_id1: [1000000000], invocation_id2: [2]}  # 1s
        optimized_runtimes = {invocation_id1: [1500000000], invocation_id2: [1]} # 1.5s (slower!)

        result = add_runtime_comments_to_generated_tests(
            test_config, generated_tests, original_runtimes, optimized_runtimes
        )

        expected_source = '''def test_function():
    codeflash_output = some_function() # 1.00s -> 1.50s (33.3% slower)
    assert codeflash_output == expected
    codeflash_output = some_function() # 2ns -> 1ns (100% faster)
    assert codeflash_output == expected
'''

        assert len(result.generated_tests) == 1
        assert result.generated_tests[0].generated_original_test_source == expected_source
