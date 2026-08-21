"""
TypeScript & TSX Parser Unit Tests (Slice ML-2)

Tests:
  - Extraction of imports (default, named, aliased, namespace, side-effect)
  - Extraction of classes, base classes (inheritance), methods, constructors
  - Extraction of functions (exported, async, generator, arrow functions, function expressions)
  - Source range integrity (start_line, end_line, line_count)
  - Docstring / JSDoc extraction
  - Call resolution states: exact / inferred / unresolved
  - TSX support (JSX components, nested elements)
  - Module name derivation for TypeScript conventions
  - Non-fabrication of interfaces / types into classes
  - Cyclomatic complexity & nesting depth
  - Error isolation: syntax errors handled gracefully without crashing
"""

import pytest
from archon.pipeline.parsers.typescript.parser import TypeScriptParser, _derive_typescript_module_name
from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ResolvedCall


@pytest.fixture
def parser():
    return TypeScriptParser()


# ---------------------------------------------------------------------------
# Module Name Derivation Tests
# ---------------------------------------------------------------------------

def test_ts_module_name_derivation():
    assert _derive_typescript_module_name("src/services/payment.service.ts") == "src/services/payment.service"
    assert _derive_typescript_module_name("src/components/Header.tsx") == "src/components/Header"
    assert _derive_typescript_module_name("types/index.d.ts") == "types/index"
    assert _derive_typescript_module_name("index.ts") == "index"
    assert _derive_typescript_module_name("src\\utils\\math.ts") == "src/utils/math"
    assert _derive_typescript_module_name("./components/Button.tsx") == "components/Button"


# ---------------------------------------------------------------------------
# Imports Extraction Tests
# ---------------------------------------------------------------------------

def test_ts_imports_extraction(parser):
    code = """
import React, { useState, useEffect as useAsyncEffect } from 'react';
import * as utils from './utils';
import config from '../config';
import './globals.css';
"""
    result = parser.parse_file("src/App.tsx", code)

    assert result.language == "typescript"
    assert result.module_name == "src/App"
    assert len(result.imports) >= 4

    # Default import
    defaults = [i for i in result.imports if i.name == "React" and not i.is_from_import]
    assert len(defaults) == 1
    assert defaults[0].module == "react"

    # Named imports
    named = [i for i in result.imports if i.is_from_import]
    assert any(i.name == "useState" and i.alias is None for i in named)
    assert any(i.name == "useEffect" and i.alias == "useAsyncEffect" for i in named)

    # Namespace import
    ns = [i for i in result.imports if i.name == "utils" and i.alias == "utils"]
    assert len(ns) == 1
    assert ns[0].module == "./utils"

    # Side-effect import
    side_effects = [i for i in result.imports if i.module == "./globals.css"]
    assert len(side_effects) == 1


# ---------------------------------------------------------------------------
# Class & Inheritance Extraction Tests
# ---------------------------------------------------------------------------

def test_ts_class_extraction(parser):
    code = """
/**
 * Payment processing service
 */
export class PaymentService extends BaseService {
    private apiKey: string;

    constructor(apiKey: string) {
        super();
        this.apiKey = apiKey;
    }

    /**
     * Process transaction
     */
    async process(amount: number): Promise<boolean> {
        this.validate(amount);
        utils.log('Processing');
        unresolvedCall();
        return true;
    }

    private validate(amount: number): void {}
}
"""
    result = parser.parse_file("src/services/payment.ts", code)

    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "PaymentService"
    assert cls.qualified_name == "src/services/payment.PaymentService"
    assert cls.base_classes == ["BaseService"]
    assert cls.start_line == 5
    assert cls.end_line >= 24
    assert cls.line_count == cls.end_line - cls.start_line + 1
    assert "Payment processing service" in (cls.docstring or "")

    # Methods
    assert len(cls.methods) == 3
    method_names = [m.name for m in cls.methods]
    assert "constructor" in method_names
    assert "process" in method_names
    assert "validate" in method_names

    process_method = [m for m in cls.methods if m.name == "process"][0]
    assert process_method.is_async is True
    assert process_method.is_method is True
    assert process_method.qualified_name == "src/services/payment.PaymentService.process"
    assert process_method.return_annotation == "Promise<boolean>"
    assert len(process_method.parameters) == 1
    assert process_method.parameters[0].name == "amount"
    assert process_method.parameters[0].type_annotation == "number"
    assert "Process transaction" in (process_method.docstring or "")


# ---------------------------------------------------------------------------
# Function & Arrow Function Extraction Tests
# ---------------------------------------------------------------------------

def test_ts_functions_and_arrow_functions(parser):
    code = """
export async function authenticate(token: string): Promise<string> {
    return utils.verify(token);
}

export const calculateTotal = (items: any[]): number => {
    return items.length;
};

export const createHandler = function(name: string) {
    return () => name;
};
"""
    result = parser.parse_file("src/utils.ts", code)

    assert len(result.functions) == 3
    func_map = {f.name: f for f in result.functions}

    # Named function
    auth = func_map["authenticate"]
    assert auth.is_async is True
    assert auth.is_method is False
    assert auth.qualified_name == "src/utils.authenticate"
    assert auth.return_annotation == "Promise<string>"
    assert auth.parameters[0].name == "token"
    assert auth.parameters[0].type_annotation == "string"

    # Arrow function with variable declarator
    calc = func_map["calculateTotal"]
    assert calc.is_async is False
    assert calc.is_method is False
    assert calc.qualified_name == "src/utils.calculateTotal"
    assert calc.return_annotation == "number"

    # Function expression
    handler = func_map["createHandler"]
    assert handler.is_method is False
    assert handler.parameters[0].name == "name"


# ---------------------------------------------------------------------------
# Call Resolution Semantics Tests (Exact / Inferred / Unresolved)
# ---------------------------------------------------------------------------

def test_ts_call_resolution_semantics(parser):
    code = """
class OrderProcessor {
    execute() {
        this.validate();
        super.init();
        localHelper();
        service.charge();
        client.api.v1.post();
    }
    validate() {}
}

function moduleFunc() {
    standaloneCall();
    externalLib.run();
}
"""
    result = parser.parse_file("order.ts", code)

    cls = result.classes[0]
    exec_method = [m for m in cls.methods if m.name == "execute"][0]
    calls = {c.raw_name: c.resolution for c in exec_method.calls}

    # this.validate() -> inferred
    assert calls["validate"] == "inferred"
    # super.init() -> inferred
    assert calls["init"] == "inferred"
    # localHelper() -> inferred (bare name in scope)
    assert calls["localHelper"] == "inferred"
    # service.charge() -> unresolved (external receiver)
    assert calls["charge"] == "unresolved"
    # client.api.v1.post() -> unresolved
    assert calls["post"] == "unresolved"

    # Module function calls
    func = result.functions[0]
    func_calls = {c.raw_name: c.resolution for c in func.calls}
    assert func_calls["standaloneCall"] == "inferred"
    assert func_calls["run"] == "unresolved"


# ---------------------------------------------------------------------------
# TSX / JSX Support Tests
# ---------------------------------------------------------------------------

def test_tsx_component_parsing(parser):
    code = """
import React, { FC } from 'react';
import { Header } from './Header';

interface Props {
    title: string;
}

export const Dashboard: FC<Props> = ({ title }) => {
    return (
        <div className="dashboard-container">
            <Header title={title} />
            <main>
                <p>Welcome to Archon Intelligence</p>
            </main>
        </div>
    );
};

export function Footer() {
    return <footer>Archon &copy; 2026</footer>;
}
"""
    result = parser.parse_file("src/components/Dashboard.tsx", code)

    assert result.language == "typescript"
    assert result.module_name == "src/components/Dashboard"
    assert len(result.parse_errors) == 0

    # Components extracted as functions
    func_names = [f.name for f in result.functions]
    assert "Dashboard" in func_names
    assert "Footer" in func_names

    # Imports extracted
    import_modules = [i.module for i in result.imports]
    assert "react" in import_modules
    assert "./Header" in import_modules


# ---------------------------------------------------------------------------
# Interfaces / Types / Enums Honesty Tests
# ---------------------------------------------------------------------------

def test_interfaces_and_types_not_fabricated(parser):
    """
    Archon rule: Do not pretend an interface is a class.
    Interfaces and type aliases should not be converted into ParsedClass.
    """
    code = """
export interface UserRecord {
    id: string;
    email: string;
}

export type UserRole = 'admin' | 'viewer' | 'editor';

export enum AccountStatus {
    Active = 'ACTIVE',
    Suspended = 'SUSPENDED'
}
"""
    result = parser.parse_file("src/types/user.ts", code)

    assert result.language == "typescript"
    assert len(result.classes) == 0  # Interfaces/types are NOT fabricated into classes
    assert len(result.functions) == 0
    assert len(result.parse_errors) == 0


# ---------------------------------------------------------------------------
# Cyclomatic Complexity & Nesting Depth Tests
# ---------------------------------------------------------------------------

def test_ts_complexity_and_nesting(parser):
    code = """
function complexLogic(x: number, y: number): boolean {
    if (x > 0 && y > 0) {
        for (let i = 0; i < x; i++) {
            while (y > 0) {
                if (i === y) {
                    return true;
                }
                y--;
            }
        }
    }
    return x ? true : false;
}
"""
    result = parser.parse_file("src/logic.ts", code)

    func = result.functions[0]
    assert func.cyclomatic_complexity >= 5  # if + && + for + while + if + ternary
    assert func.nesting_depth >= 3          # if -> for -> while -> if


# ---------------------------------------------------------------------------
# Error Isolation & Safe Recovery Tests
# ---------------------------------------------------------------------------

def test_ts_syntax_error_does_not_raise(parser):
    broken_code = """
export class BrokenClass {
    def invalid syntax () {{{
"""
    result = parser.parse_file("src/broken.ts", broken_code)

    assert result.language == "typescript"
    assert result.module_name == "src/broken"
    assert isinstance(result.classes, list)
    assert isinstance(result.functions, list)
    assert isinstance(result.imports, list)


def test_ts_empty_file(parser):
    result = parser.parse_file("empty.ts", "")
    assert result.language == "typescript"
    assert result.module_name == "empty"
    assert result.total_lines == 0
    assert len(result.classes) == 0
    assert len(result.functions) == 0
