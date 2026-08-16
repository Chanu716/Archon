import pytest
import ast
from archon.pipeline.parsers.python.parser import PythonVisitor

def test_nesting_depth_calculation():
    code = """
def heavily_nested(x):
    if x > 0:            # 1
        for i in range(x): # 2
            try:           # 3
                if i == 5: # 4
                    print(i)
            except:
                pass
    return x
"""
    tree = ast.parse(code)
    visitor = PythonVisitor("test")
    visitor.visit(tree)
    
    assert len(visitor.functions) == 1
    func = visitor.functions[0]
    
    assert func.nesting_depth == 4
    
def test_flat_nesting_depth():
    code = """
def flat(x):
    print(x)
    return x
"""
    tree = ast.parse(code)
    visitor = PythonVisitor("test")
    visitor.visit(tree)
    
    assert visitor.functions[0].nesting_depth == 0
