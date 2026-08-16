import pytest
from archon.pipeline.parsers.python.parser import PythonParser

def test_python_parser_extraction():
    parser = PythonParser()
    code = '''
"""Module docstring"""
import os
from collections import defaultdict

class Processor:
    """Class docstring"""
    def __init__(self):
        self.data = []
        
    def process(self):
        """Method docstring"""
        self.helper()
        os.path.join('a', 'b')
        unresolved_call()

def module_func():
    Processor().process()
'''
    parsed = parser.parse_file("test_module.py", code)
    
    assert parsed.language == "python"
    assert parsed.docstring == "Module docstring"
    assert len(parsed.imports) == 2
    
    assert len(parsed.classes) == 1
    cls = parsed.classes[0]
    assert cls.name == "Processor"
    assert cls.docstring == "Class docstring"
    assert len(cls.methods) == 2
    
    method = cls.methods[1]
    assert method.name == "process"
    assert method.docstring == "Method docstring"
    
    # Check calls in method
    call_names = {c.raw_name: c.resolution for c in method.calls}
    assert call_names["helper"] == "inferred" # self.helper
    assert call_names["join"] == "unresolved" # os.path.join
    assert call_names["unresolved_call"] == "inferred" # bare name, so inferred
    
    assert len(parsed.functions) == 1
    func = parsed.functions[0]
    assert func.name == "module_func"
    assert func.calls[0].raw_name == "process"
    assert func.calls[0].resolution == "unresolved" # Processor().process -> attribute call on non-self
