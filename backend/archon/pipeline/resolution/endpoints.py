"""
API & HTTP Endpoint Cross-Language Resolution (ML-4)

Extracts backend API route definitions (FastAPI, Flask) and frontend HTTP client
calls (fetch, axios) to deterministically link frontend callers to backend handlers.
"""

import ast
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
import structlog
from tree_sitter import Language, Parser, Node
import tree_sitter_typescript as tst
import tree_sitter_javascript as js_lang
import tree_sitter_c_sharp as ts_csharp
import tree_sitter_go as ts_go

from archon.pipeline.parsers.base import ParsedFile, ParsedFunction
from archon.pipeline.resolution.base import BaseResolver
from archon.pipeline.resolution.models import ResolutionResult

logger = structlog.get_logger(__name__)

TS_LANG = Language(tst.language_typescript())
TSX_LANG = Language(tst.language_tsx())
JS_LANG = Language(js_lang.language())
CS_LANG = Language(ts_csharp.language())
GO_LANG = Language(ts_go.language())


@dataclass
class BackendRoute:
    """Represents a statically discovered backend route declaration."""
    method: str              # "GET", "POST", "PUT", "DELETE", "PATCH", etc.
    path: str                # e.g. "/api/v1/users"
    handler_qualified_name: str
    file_path: str
    framework: str           # "fastapi" | "flask" | "aspnetcore" | "aspnetcore-minimal"
    language: str = "python"


@dataclass
class FrontendHttpCall:
    """Represents a statically discovered frontend HTTP client call."""
    method: str              # "GET", "POST", etc.
    path: str                # e.g. "/api/v1/users"
    caller_qualified_name: str
    file_path: str
    client: str              # "fetch" | "axios"
    is_dynamic: bool = False


def _normalize_http_path(path: str) -> str:
    """Normalizes HTTP path: ensures leading slash, collapses multiple slashes, strips trailing slash (except root)."""
    p = path.strip()
    p = re.sub(r"/+", "/", p)
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def _normalize_param_path(path: str) -> str:
    """
    Normalizes path parameters to a standard comparison format.
    e.g. '/users/{user_id}' -> '/users/{_}'
         '/users/<user_id>' -> '/users/{_}'
         '/users/:user_id'  -> '/users/{_}'
    """
    p = _normalize_http_path(path)
    # Replace FastAPI / ASP.NET {param}
    p = re.sub(r"\{[a-zA-Z0-9_]+\}", "{_}", p)
    # Replace Flask <param> or <type:param>
    p = re.sub(r"<([a-zA-Z0-9_]+:)?[a-zA-Z0-9_]+>", "{_}", p)
    # Replace Express/JS :param
    p = re.sub(r":([a-zA-Z0-9_]+)", "{_}", p)
    return p


class EndpointResolver(BaseResolver):
    """
    Deterministically extracts:
      1. Backend route declarations from Python (FastAPI, Flask) & C# (ASP.NET Core)
      2. Frontend HTTP calls from TypeScript/JavaScript files (fetch, axios)
      3. Connects frontend callers -> Endpoint node -> backend handlers via REQUESTS & HANDLED_BY.
    """

    def __init__(self):
        self._ts_parser = Parser(TS_LANG)
        self._tsx_parser = Parser(TSX_LANG)
        self._js_parser = Parser(JS_LANG)
        self._cs_parser = Parser(CS_LANG)
        self._go_parser = Parser(GO_LANG)

    def resolve(
        self,
        parsed_files: List[ParsedFile],
        file_contents: Optional[Dict[str, str]] = None
    ) -> List[ResolutionResult]:
        results: List[ResolutionResult] = []

        backend_routes: List[BackendRoute] = []
        frontend_calls: List[FrontendHttpCall] = []

        # 1. Extract backend routes and frontend HTTP calls
        for pfile in parsed_files:
            # We can use raw content if provided, or read content from file path
            content = None
            if file_contents and pfile.path in file_contents:
                content = file_contents[pfile.path]

            if pfile.language == "python":
                routes = self._extract_python_routes(pfile, content)
                backend_routes.extend(routes)
            elif pfile.language == "csharp":
                routes = self._extract_csharp_routes(pfile, content)
                backend_routes.extend(routes)
            elif pfile.language == "go":
                routes = self._extract_go_routes(pfile, content)
                backend_routes.extend(routes)
            elif pfile.language == "rust":
                routes = self._extract_rust_routes(pfile, content)
                backend_routes.extend(routes)
            elif pfile.language in ("typescript", "javascript"):
                calls = self._extract_js_ts_http_calls(pfile, content)
                frontend_calls.extend(calls)

        if not backend_routes or not frontend_calls:
            return results

        # 2. Index backend routes by (METHOD, NORMALIZED_PARAM_PATH)
        routes_by_key: Dict[Tuple[str, str], List[BackendRoute]] = {}
        for route in backend_routes:
            key = (route.method.upper(), _normalize_param_path(route.path))
            routes_by_key.setdefault(key, []).append(route)

        # 3. Match frontend calls to backend routes
        for call in frontend_calls:
            if call.is_dynamic:
                # Dynamic URLs cannot be proven exact statically
                continue

            call_key = (call.method.upper(), _normalize_param_path(call.path))
            matching_routes = routes_by_key.get(call_key, [])

            if len(matching_routes) == 1:
                matched_route = matching_routes[0]
                norm_endpoint_path = _normalize_http_path(call.path)
                endpoint_id = f"endpoint:{call.method.upper()}:{norm_endpoint_path}"

                # 1. Caller Function -[:REQUESTS]-> Endpoint
                results.append(ResolutionResult(
                    source_id=call.caller_qualified_name,
                    target_id=endpoint_id,
                    relationship="REQUESTS",
                    resolution="exact",
                    evidence_type="static_http_route",
                    reason=f"Frontend {call.client} call '{call.method} {call.path}' matches backend route in '{matched_route.file_path}'",
                    source_language="typescript" if call.file_path.endswith((".ts", ".tsx")) else "javascript",
                    target_language=matched_route.language,
                    source_file=call.file_path,
                    target_file=matched_route.file_path,
                    metadata={
                        "http_method": call.method.upper(),
                        "path": norm_endpoint_path,
                        "handler_qname": matched_route.handler_qualified_name,
                        "framework": matched_route.framework,
                        "client": call.client
                    }
                ))

                # 2. Endpoint -[:HANDLED_BY]-> Backend Handler Function
                results.append(ResolutionResult(
                    source_id=endpoint_id,
                    target_id=matched_route.handler_qualified_name,
                    relationship="HANDLED_BY",
                    resolution="exact",
                    evidence_type="static_http_route",
                    reason=f"Backend handler for endpoint '{call.method} {norm_endpoint_path}'",
                    source_language=matched_route.language,
                    target_language=matched_route.language,
                    source_file=matched_route.file_path,
                    target_file=matched_route.file_path,
                    metadata={
                        "http_method": call.method.upper(),
                        "path": norm_endpoint_path,
                        "framework": matched_route.framework
                    }
                ))

            elif len(matching_routes) > 1:
                logger.warning(
                    "ambiguous_endpoint_resolution",
                    method=call.method,
                    path=call.path,
                    matching_handlers=[r.handler_qualified_name for r in matching_routes]
                )

        logger.info(
            "endpoint_resolution_complete",
            backend_routes_count=len(backend_routes),
            frontend_calls_count=len(frontend_calls),
            resolved_count=len(results)
        )
        return results

    # ── Python Backend Route Extraction ────────────────────────────────────────

    def _extract_python_routes(self, pfile: ParsedFile, content: Optional[str]) -> List[BackendRoute]:
        """Extracts FastAPI and Flask route declarations from Python AST."""
        routes: List[BackendRoute] = []
        if not content:
            return routes

        try:
            tree = ast.parse(content)
        except Exception:
            return routes

        # Check for router prefix definitions (e.g. router = APIRouter(prefix="/api/v1"))
        router_prefixes: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        # APIRouter(prefix="/api")
                        call = node.value
                        fn_name = getattr(call.func, "id", getattr(call.func, "attr", ""))
                        if fn_name in ("APIRouter", "Blueprint"):
                            for kw in call.keywords:
                                if kw.arg in ("prefix", "url_prefix") and isinstance(kw.value, ast.Constant):
                                    router_prefixes[target.id] = str(kw.value.value)

        # Inspect function decorators
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                func_qname = f"{pfile.module_name}.{func_name}" if pfile.module_name else f"{pfile.path}.{func_name}"

                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        attr = dec.func.attr.lower()
                        obj_name = getattr(dec.func.value, "id", getattr(dec.func.value, "attr", ""))

                        prefix = router_prefixes.get(obj_name, "")
                        http_methods: List[str] = []
                        route_path: Optional[str] = None
                        framework = "fastapi"

                        # FastAPI standard decorators: @app.get("/users"), @router.post("/payments")
                        if attr in ("get", "post", "put", "delete", "patch", "options", "head"):
                            http_methods = [attr.upper()]
                            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                                route_path = dec.args[0].value
                            framework = "fastapi"

                        # Flask or generic @app.route("/path", methods=["GET", "POST"])
                        elif attr == "route":
                            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                                route_path = dec.args[0].value

                            # Check methods keyword
                            methods_found = []
                            for kw in dec.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                                    for elt in kw.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                             methods_found.append(elt.value.upper())
                            http_methods = methods_found if methods_found else ["GET"]
                            framework = "flask"

                        if route_path and http_methods:
                            full_path = _normalize_http_path(prefix + "/" + route_path.lstrip("/"))
                            for m in http_methods:
                                routes.append(BackendRoute(
                                    method=m,
                                    path=full_path,
                                    handler_qualified_name=func_qname,
                                    file_path=pfile.path,
                                    framework=framework,
                                    language="python"
                                ))

        return routes

    # ── C# ASP.NET Core Route & Minimal API Extraction ────────────────────────

    def _extract_csharp_routes(self, pfile: ParsedFile, content: Optional[str]) -> List[BackendRoute]:
        """Extracts ASP.NET Core controller and minimal API route declarations."""
        routes: List[BackendRoute] = []
        if not content:
            return routes

        source_bytes = content.encode("utf-8", errors="replace")
        tree = self._cs_parser.parse(source_bytes)

        def text(n: Node) -> str:
            return source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

        # 1. Extract namespace from file
        namespace = None
        for child in tree.root_node.children:
            if child.type in ("file_scoped_namespace_declaration", "namespace_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    namespace = text(name_node)

        # 2. Walk AST for controllers and minimal APIs
        def walk_csharp(n: Node, current_class: Optional[str] = None, current_class_route: str = ""):
            if n.type == "class_declaration":
                cname_node = n.child_by_field_name("name")
                cname = text(cname_node) if cname_node else ""
                class_route = ""

                # Check class-level attributes e.g. [Route("api/[controller]")]
                for c in n.children:
                    if c.type == "attribute_list":
                        for attr in c.children:
                            if attr.type == "attribute":
                                attr_text = text(attr)
                                m = re.match(r'Route\s*\(\s*"([^"]+)"\s*\)', attr_text)
                                if m:
                                    r_tpl = m.group(1)
                                    # Replace [controller] token with class name minus 'Controller' suffix
                                    ctrl_token = cname
                                    if ctrl_token.endswith("Controller"):
                                        ctrl_token = ctrl_token[:-10]
                                    class_route = r_tpl.replace("[controller]", ctrl_token.lower()).replace("[Controller]", ctrl_token)

                for c in n.children:
                    walk_csharp(c, cname, class_route)
                return

            elif n.type == "method_declaration":
                mname_node = n.child_by_field_name("name")
                mname = text(mname_node) if mname_node else ""
                method_qname = f"{namespace}.{current_class}.{mname}" if namespace and current_class else (f"{pfile.module_name}.{mname}" if pfile.module_name else mname)

                for c in n.children:
                    if c.type == "attribute_list":
                        for attr in c.children:
                            if attr.type == "attribute":
                                attr_text = text(attr)
                                # [HttpGet], [HttpGet("{id}")], [HttpPost("orders/{id}")]
                                m_http = re.match(r'Http(Get|Post|Put|Delete|Patch)\s*(\(\s*"([^"]*)"\s*\))?', attr_text)
                                if m_http:
                                    http_verb = m_http.group(1).upper()
                                    sub_path = m_http.group(3) or ""
                                    full_path = _normalize_http_path(f"/{current_class_route.strip('/')}/{sub_path.strip('/')}")
                                    routes.append(BackendRoute(
                                        method=http_verb,
                                        path=full_path,
                                        handler_qualified_name=method_qname,
                                        file_path=pfile.path,
                                        framework="aspnetcore",
                                        language="csharp"
                                    ))
                                elif attr_text.startswith("Route("):
                                    m_r = re.match(r'Route\s*\(\s*"([^"]+)"\s*\)', attr_text)
                                    if m_r:
                                        sub_path = m_r.group(1)
                                        full_path = _normalize_http_path(f"/{current_class_route.strip('/')}/{sub_path.strip('/')}")
                                        routes.append(BackendRoute(
                                            method="GET",
                                            path=full_path,
                                            handler_qualified_name=method_qname,
                                            file_path=pfile.path,
                                            framework="aspnetcore",
                                            language="csharp"
                                        ))

            elif n.type == "invocation_expression":
                expr_node = n.child_by_field_name("function")
                args_node = n.child_by_field_name("arguments")
                if expr_node and expr_node.type == "member_access_expression" and args_node:
                    fn_name_node = expr_node.child_by_field_name("name")
                    if fn_name_node:
                        fn_name = text(fn_name_node)
                        # app.MapGet, app.MapPost, app.MapPut, app.MapDelete, app.MapPatch
                        m_map = re.match(r'Map(Get|Post|Put|Delete|Patch)', fn_name)
                        if m_map and args_node.named_child_count >= 1:
                            http_verb = m_map.group(1).upper()
                            path_arg = args_node.named_children[0]
                            path_val = _normalize_http_path(text(path_arg).strip('"\''))
                            handler_qname = f"{namespace or pfile.module_name}.Program.{fn_name}"
                            if args_node.named_child_count >= 2:
                                handler_arg = args_node.named_children[1]
                                if handler_arg.type == "identifier":
                                    h_name = text(handler_arg)
                                    handler_qname = f"{namespace or pfile.module_name}.Program.{h_name}"

                            routes.append(BackendRoute(
                                method=http_verb,
                                path=path_val,
                                handler_qualified_name=handler_qname,
                                file_path=pfile.path,
                                framework="aspnetcore-minimal",
                                language="csharp"
                            ))

            for c in n.children:
                walk_csharp(c, current_class, current_class_route)

        walk_csharp(tree.root_node)
        return routes

    # ── Go Web Framework Route Extraction ────────────────────────────────────

    def _extract_go_routes(self, pfile: ParsedFile, content: Optional[str]) -> List[BackendRoute]:
        """Extracts Go web framework route declarations (Gin, Echo, Fiber, Chi, net/http)."""
        routes: List[BackendRoute] = []
        if not content:
            return routes

        source_bytes = content.encode("utf-8", errors="replace")
        tree = self._go_parser.parse(source_bytes)

        def text(n: Node) -> str:
            return source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

        # 1. Extract package name from file
        package_name = None
        for child in tree.root_node.children:
            if child.type == "package_clause":
                for sub in child.children:
                    if sub.type == "package_identifier":
                        package_name = text(sub)
                        break

        module_name = pfile.module_name or package_name or "main"

        # 2. Track route group prefixes e.g. api := r.Group("/api/v1")
        group_prefixes: Dict[str, str] = {}

        def walk_go(n: Node):
            if n.type == "short_var_declaration":
                # api := r.Group("/api/v2")
                left = n.child_by_field_name("left")
                right = n.child_by_field_name("right")
                if left and right:
                    var_name = text(left)
                    for call in right.children:
                        if call.type == "call_expression":
                            fn = call.child_by_field_name("function")
                            args = call.child_by_field_name("arguments")
                            if fn and text(fn).endswith(".Group") and args and args.named_child_count >= 1:
                                prefix_val = text(args.named_children[0]).strip('"\'`')
                                group_prefixes[var_name] = prefix_val

            elif n.type == "call_expression":
                fn = n.child_by_field_name("function")
                args = n.child_by_field_name("arguments")
                if fn and fn.type == "selector_expression" and args and args.named_child_count >= 2:
                    rec = fn.child_by_field_name("operand")
                    field = fn.child_by_field_name("field")
                    if rec and field:
                        rec_name = text(rec)
                        verb = text(field).upper()
                        if verb in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                            path_val = text(args.named_children[0]).strip('"\'`')
                            handler_val = text(args.named_children[1])
                            prefix = group_prefixes.get(rec_name, "")
                            full_path = _normalize_http_path(f"/{prefix.strip('/')}/{path_val.strip('/')}")
                            handler_qname = f"{module_name}.{handler_val}"
                            routes.append(BackendRoute(
                                method=verb,
                                path=full_path,
                                handler_qualified_name=handler_qname,
                                file_path=pfile.path,
                                framework="gin",
                                language="go"
                            ))
                        elif verb in ("HANDLEFUNC", "HANDLE"):
                            path_val = text(args.named_children[0]).strip('"\'`')
                            handler_val = text(args.named_children[1])
                            full_path = _normalize_http_path(path_val)
                            handler_qname = f"{module_name}.{handler_val}"
                            routes.append(BackendRoute(
                                method="GET",
                                path=full_path,
                                handler_qualified_name=handler_qname,
                                file_path=pfile.path,
                                framework="net/http",
                                language="go"
                            ))

            for c in n.children:
                walk_go(c)

        walk_go(tree.root_node)
        return routes

    # ── JavaScript / TypeScript HTTP Call Extraction ──────────────────────────

    def _extract_js_ts_http_calls(self, pfile: ParsedFile, content: Optional[str]) -> List[FrontendHttpCall]:
        """Extracts fetch and axios HTTP client calls using tree-sitter."""
        calls: List[FrontendHttpCall] = []
        if not content:
            return calls

        source_bytes = content.encode("utf-8", errors="replace")

        if pfile.path.endswith(".tsx"):
            tree = self._tsx_parser.parse(source_bytes)
        elif pfile.path.endswith((".ts", ".d.ts")):
            tree = self._ts_parser.parse(source_bytes)
        else:
            tree = self._js_parser.parse(source_bytes)

        # Helper to get UTF-8 text
        def text(n: Node) -> str:
            return source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

        # Walk AST keeping track of current containing function
        def walk_for_http_calls(n: Node, current_func_qname: str):
            # Check if this node introduces a new function scope
            func_scope = current_func_qname
            if n.type in ("function_declaration", "generator_function_declaration"):
                name_node = n.child_by_field_name("name")
                if name_node:
                    func_scope = f"{pfile.module_name or pfile.path}.{text(name_node)}"
            elif n.type == "variable_declarator":
                name_node = n.child_by_field_name("name")
                val_node = n.child_by_field_name("value")
                if name_node and val_node and val_node.type in ("arrow_function", "function_expression"):
                    func_scope = f"{pfile.module_name or pfile.path}.{text(name_node)}"
            elif n.type == "method_definition":
                name_node = n.child_by_field_name("name")
                if name_node:
                    func_scope = f"{pfile.module_name or pfile.path}.{text(name_node)}"

            # Inspect call expressions
            if n.type == "call_expression":
                fn_node = n.child_by_field_name("function")
                args_node = n.child_by_field_name("arguments")

                if fn_node and args_node and args_node.named_child_count >= 1:
                    fn_text = text(fn_node)
                    arg0 = args_node.named_children[0]

                    # 1. fetch('/api/users', options?)
                    if fn_text == "fetch":
                        is_dynamic = (arg0.type == "template_string" and "${" in text(arg0))
                        url_text = text(arg0).strip("'\"`")
                        method = "GET"

                        # Check options object if provided: fetch(url, { method: 'POST' })
                        if args_node.named_child_count >= 2:
                            arg1 = args_node.named_children[1]
                            if arg1.type == "object":
                                for prop in arg1.named_children:
                                    if prop.type in ("pair", "property"):
                                        k = prop.child_by_field_name("key")
                                        v = prop.child_by_field_name("value")
                                        if k and v and text(k).strip("'\"`") == "method":
                                            method = text(v).strip("'\"`").upper()

                        if url_text.startswith("/") or not is_dynamic:
                            calls.append(FrontendHttpCall(
                                method=method,
                                path=url_text,
                                caller_qualified_name=func_scope,
                                file_path=pfile.path,
                                client="fetch",
                                is_dynamic=is_dynamic
                            ))

                    # 2. axios.get('/api/users'), axios.post('/api/payments', data)
                    elif "." in fn_text:
                        parts = fn_text.split(".")
                        receiver = parts[0]
                        method_name = parts[-1].lower()

                        if receiver in ("axios", "apiClient", "client", "http", "api", "instance"):
                            if method_name in ("get", "post", "put", "delete", "patch", "head", "options"):
                                is_dynamic = (arg0.type == "template_string" and "${" in text(arg0))
                                url_text = text(arg0).strip("'\"`")
                                calls.append(FrontendHttpCall(
                                    method=method_name.upper(),
                                    path=url_text,
                                    caller_qualified_name=func_scope,
                                    file_path=pfile.path,
                                    client="axios",
                                    is_dynamic=is_dynamic
                                ))

            for child in n.children:
                walk_for_http_calls(child, func_scope)

        default_scope = pfile.module_name or pfile.path
        walk_for_http_calls(tree.root_node, default_scope)
        return calls

    # ── Rust Backend Route Extraction ────────────────────────────────────────

    _AXUM_ROUTE_RE = re.compile(
        r'\.route\(\s*["\']([^"\']+)["\']\s*,\s*(get|post|put|delete|patch|options|head)\s*\(\s*([a-zA-Z0-9_]+)\s*\)',
        re.IGNORECASE
    )
    _ACTIX_ROCKET_ATTR_RE = re.compile(
        r'#\[\s*(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\]'
        r'\s*(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)',
        re.IGNORECASE
    )

    def _extract_rust_routes(self, pfile: ParsedFile, content: Optional[str]) -> List[BackendRoute]:
        """
        Extracts Axum, Actix Web, and Rocket route declarations from Rust source.

        Supported static patterns (no macro expansion):
          Axum:         Router::new().route("/path", get(handler))
          Actix Web:    #[get("/path")] async fn handler()
          Rocket:       #[get("/path")] fn handler()

        Dynamic routes (runtime-computed paths) remain unresolved.
        """
        routes: List[BackendRoute] = []
        if not content:
            return routes

        module_name = pfile.module_name or pfile.path
        # Detect framework from imports / content (static text scan only)
        content_lower = content[:2000].lower()
        if "actix_web" in content_lower or "actix-web" in content_lower:
            framework = "actix"
        elif "rocket" in content_lower:
            framework = "rocket"
        else:
            framework = "axum"  # Default for attribute-style with router

        # 1. Axum: .route("/path", get(handler))
        for m in self._AXUM_ROUTE_RE.finditer(content):
            path, method, handler = m.group(1), m.group(2).upper(), m.group(3)
            handler_qname = f"{module_name}.{handler}"
            routes.append(BackendRoute(
                method=method,
                path=path,
                handler_qualified_name=handler_qname,
                file_path=pfile.path,
                framework="axum",
                language="rust",
            ))

        # 2. Actix / Rocket: #[get("/path")] [pub] [async] fn handler()
        for m in self._ACTIX_ROCKET_ATTR_RE.finditer(content):
            method, path, handler = m.group(1).upper(), m.group(2), m.group(3)
            handler_qname = f"{module_name}.{handler}"
            routes.append(BackendRoute(
                method=method,
                path=path,
                handler_qualified_name=handler_qname,
                file_path=pfile.path,
                framework=framework,
                language="rust",
            ))

        return routes
