"""
JavaScript & JSX Parser Unit Tests (Slice ML-3)

Tests:
  - Extraction of ES Module imports (default, named, aliased, namespace, side-effect)
  - Extraction of CommonJS literal require() imports (single variable, destructured)
  - Rejection / non-fabrication of dynamic require() calls
  - Extraction of classes, inheritance (extends Base), constructors, methods, async methods
  - Omission of anonymous default classes (export default class {})
  - Extraction of functions (named, async, generator function*, arrow functions, function expressions)
  - Extraction of stable object literal methods (const service = { process() {}, ... })
  - Omission of anonymous callbacks (e.g. items.map(x => x.id), setTimeout(() => {}, 1000))
  - Source range integrity (start_line, end_line, line_count)
  - Docstring / JSDoc extraction
  - Call resolution states: exact / inferred / unresolved
  - JSX support (JSX components, nested elements)
  - Module name derivation for .js, .jsx, .mjs, .cjs, and Windows path separators
  - Cyclomatic complexity & nesting depth
  - Error isolation: syntax errors handled gracefully without crashing
"""

import pytest
from archon.pipeline.parsers.javascript.parser import JavaScriptParser, _derive_javascript_module_name
from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ResolvedCall


@pytest.fixture
def parser():
    return JavaScriptParser()


# ---------------------------------------------------------------------------
# Module Name Derivation Tests
# ---------------------------------------------------------------------------

def test_js_module_name_derivation():
    assert _derive_javascript_module_name("src/components/Button.jsx") == "src/components/Button"
    assert _derive_javascript_module_name("utils/math.js") == "utils/math"
    assert _derive_javascript_module_name("lib/esm/index.mjs") == "lib/esm/index"
    assert _derive_javascript_module_name("config/db.cjs") == "config/db"
    assert _derive_javascript_module_name("index.js") == "index"
    assert _derive_javascript_module_name("src\\utils\\file.js") == "src/utils/file"
    assert _derive_javascript_module_name("./components/Header.jsx") == "components/Header"


# ---------------------------------------------------------------------------
# Imports Extraction Tests (ES Module & CommonJS require)
# ---------------------------------------------------------------------------

def test_js_esm_and_commonjs_imports(parser):
    code = """
import React, { useState, useEffect as useAsyncEffect } from 'react';
import * as utils from './utils';
import config from '../config';
import './globals.css';

const fs = require('fs');
const { join, resolve: resPath } = require('path');
const dynamic = require(dynamicVar);
require('./polyfill');
"""
    result = parser.parse_file("src/index.js", code)

    assert result.language == "javascript"
    assert result.module_name == "src/index"

    # ES Module Default
    defaults = [i for i in result.imports if i.name == "React" and not i.is_from_import]
    assert len(defaults) == 1
    assert defaults[0].module == "react"

    # ES Module Named
    named = [i for i in result.imports if i.is_from_import]
    assert any(i.name == "useState" and i.alias is None and i.module == "react" for i in named)
    assert any(i.name == "useEffect" and i.alias == "useAsyncEffect" and i.module == "react" for i in named)

    # ES Module Namespace
    ns = [i for i in result.imports if i.name == "utils" and i.alias == "utils"]
    assert len(ns) == 1
    assert ns[0].module == "./utils"

    # Side-effect ES import
    assert any(i.module == "./globals.css" for i in result.imports)

    # CommonJS literal require('fs')
    fs_imports = [i for i in result.imports if i.name == "fs" and i.module == "fs"]
    assert len(fs_imports) == 1

    # CommonJS destructured require('path')
    path_imports = [i for i in result.imports if i.module == "path"]
    assert any(i.name == "join" and i.alias is None for i in path_imports)
    assert any(i.name == "resolve" and i.alias == "resPath" for i in path_imports)

    # CommonJS side-effect require('./polyfill')
    assert any(i.module == "./polyfill" for i in result.imports)

    # Dynamic require(dynamicVar) MUST NOT be falsely extracted as static import
    assert not any(i.module == "dynamicVar" for i in result.imports)


# ---------------------------------------------------------------------------
# Class & Inheritance Extraction Tests
# ---------------------------------------------------------------------------

def test_js_class_extraction(parser):
    code = """
/**
 * User service class
 */
export class UserService extends BaseService {
    constructor(name) {
        super();
        this.name = name;
    }

    /**
     * Authenticate user
     */
    async login(token) {
        this.validate(token);
        utils.log('login');
        unresolvedCall();
        return true;
    }

    validate(token) {}
}

// Anonymous class should be skipped
export default class {
    anonymousMethod() {}
}
"""
    result = parser.parse_file("src/services/user.js", code)

    # Only UserService should be extracted, anonymous class safely omitted
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "UserService"
    assert cls.qualified_name == "src/services/user.UserService"
    assert cls.base_classes == ["BaseService"]
    assert cls.start_line == 5
    assert cls.end_line >= 22
    assert "User service class" in (cls.docstring or "")

    # Methods
    method_names = [m.name for m in cls.methods]
    assert "constructor" in method_names
    assert "login" in method_names
    assert "validate" in method_names

    login_m = [m for m in cls.methods if m.name == "login"][0]
    assert login_m.is_async is True
    assert login_m.is_method is True
    assert login_m.qualified_name == "src/services/user.UserService.login"
    assert len(login_m.parameters) == 1
    assert login_m.parameters[0].name == "token"
    assert "Authenticate user" in (login_m.docstring or "")


# ---------------------------------------------------------------------------
# Function, Generator, Arrow & Object Methods Extraction Tests
# ---------------------------------------------------------------------------

def test_js_functions_and_object_methods(parser):
    code = """
export async function fetchData(url) {
    return utils.get(url);
}

export function* generateIds() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

export const calculateTotal = (items) => {
    return items.length;
};

export const createHelper = function(prefix) {
    return prefix;
};

// Object literal with stable methods
const mathService = {
    add(a, b) {
        return a + b;
    },
    multiply: function(a, b) {
        return a * b;
    },
    divide: (a, b) => {
        return a / b;
    }
};

// Anonymous callbacks - must be omitted
const list = [1, 2, 3];
list.map(x => x * 2);
setTimeout(() => {
    console.log('timeout');
}, 1000);
"""
    result = parser.parse_file("src/helpers.js", code)

    func_map = {f.name: f for f in result.functions}

    # Named async function
    assert "fetchData" in func_map
    assert func_map["fetchData"].is_async is True
    assert func_map["fetchData"].qualified_name == "src/helpers.fetchData"

    # Generator function
    assert "generateIds" in func_map
    assert func_map["generateIds"].qualified_name == "src/helpers.generateIds"

    # Arrow function
    assert "calculateTotal" in func_map
    assert func_map["calculateTotal"].qualified_name == "src/helpers.calculateTotal"

    # Function expression
    assert "createHelper" in func_map
    assert func_map["createHelper"].qualified_name == "src/helpers.createHelper"

    # Object methods
    assert "mathService.add" in func_map
    assert func_map["mathService.add"].qualified_name == "src/helpers.mathService.add"
    assert "mathService.multiply" in func_map
    assert "mathService.divide" in func_map

    # Ensure anonymous callbacks did not create ghost entities
    assert not any(f.name == "" or f.name.startswith("<anonymous") for f in result.functions)


# ---------------------------------------------------------------------------
# Call Resolution Semantics Tests (Exact / Inferred / Unresolved)
# ---------------------------------------------------------------------------

def test_js_call_resolution_semantics(parser):
    code = """
class OrderHandler {
    process() {
        this.validate();
        super.init();
        localHelper();
        service.charge();
        client.api.post();
    }
    validate() {}
}

function moduleFunc() {
    standaloneCall();
    externalLib.run();
}
"""
    result = parser.parse_file("handler.js", code)

    cls = result.classes[0]
    proc_method = [m for m in cls.methods if m.name == "process"][0]
    calls = {c.raw_name: c.resolution for c in proc_method.calls}

    # this.validate() -> inferred
    assert calls["validate"] == "inferred"
    # super.init() -> inferred
    assert calls["init"] == "inferred"
    # localHelper() -> inferred (bare name in scope)
    assert calls["localHelper"] == "inferred"
    # service.charge() -> unresolved (external receiver)
    assert calls["charge"] == "unresolved"
    # client.api.post() -> unresolved
    assert calls["post"] == "unresolved"

    # Module function calls
    func = result.functions[0]
    func_calls = {c.raw_name: c.resolution for c in func.calls}
    assert func_calls["standaloneCall"] == "inferred"
    assert func_calls["run"] == "unresolved"


# ---------------------------------------------------------------------------
# JSX Support Tests (.jsx / .js)
# ---------------------------------------------------------------------------

def test_jsx_component_parsing(parser):
    code = """
import React from 'react';
import { Header } from './Header';

export const Dashboard = ({ user }) => {
    const handleSave = () => {
        saveUser();
    };

    return (
        <div className="dashboard">
            <Header title="Archon" />
            <button onClick={() => saveUser()}>Save</button>
        </div>
    );
};

export function Footer() {
    return <footer>Archon &copy; 2026</footer>;
}
"""
    result = parser.parse_file("src/components/Dashboard.jsx", code)

    assert result.language == "javascript"
    assert result.module_name == "src/components/Dashboard"
    assert len(result.parse_errors) == 0

    func_names = [f.name for f in result.functions]
    assert "Dashboard" in func_names
    assert "Footer" in func_names

    import_modules = [i.module for i in result.imports]
    assert "react" in import_modules
    assert "./Header" in import_modules


# ---------------------------------------------------------------------------
# Complexity & Nesting Tests
# ---------------------------------------------------------------------------

def test_js_complexity_and_nesting(parser):
    code = """
function processData(items, flags) {
    if (items && items.length > 0) {
        for (const item of items) {
            while (flags.active) {
                if (item.id === 10) {
                    return true;
                }
            }
        }
    }
    return flags ? true : false;
}
"""
    result = parser.parse_file("src/data.js", code)

    func = result.functions[0]
    assert func.cyclomatic_complexity >= 5  # if + && + for..of + while + if + ternary
    assert func.nesting_depth >= 3          # if -> for -> while -> if


# ---------------------------------------------------------------------------
# Error Isolation & Safe Recovery Tests
# ---------------------------------------------------------------------------

def test_js_syntax_error_does_not_raise(parser):
    broken_code = """
function broken( {
    invalid syntax {{{
"""
    result = parser.parse_file("src/broken.js", broken_code)

    assert result.language == "javascript"
    assert result.module_name == "src/broken"
    assert isinstance(result.classes, list)
    assert isinstance(result.functions, list)
    assert isinstance(result.imports, list)


def test_js_empty_file(parser):
    result = parser.parse_file("empty.js", "")
    assert result.language == "javascript"
    assert result.module_name == "empty"
    assert result.total_lines == 0
    assert len(result.classes) == 0
    assert len(result.functions) == 0


def test_mjs_and_cjs_extensions(parser):
    mjs_code = "export const PI = 3.14159;"
    cjs_code = "module.exports = { port: 8080 };"

    res_mjs = parser.parse_file("math.mjs", mjs_code)
    assert res_mjs.language == "javascript"
    assert res_mjs.module_name == "math"

    res_cjs = parser.parse_file("config.cjs", cjs_code)
    assert res_cjs.language == "javascript"
    assert res_cjs.module_name == "config"
