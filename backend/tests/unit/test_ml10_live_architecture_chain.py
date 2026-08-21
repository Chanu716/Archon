"""
Live Architecture Chain Verification (Slice ML-10)

Tests the complete end-to-end polyglot architecture chain:
  1. Frontend TSX Component (CheckoutButton.tsx)
       └── exact CALLS ──> TypeScript API Client (checkoutClient.ts)
  2. TypeScript API Client
       └── REQUESTS ──> POST /api/v1/orders
  3. POST /api/v1/orders
       └── HANDLED_BY ──> C# OrderController.Checkout (OrderController.cs)
  4. OrderController
       ├── DEPENDS_ON ──> OrderService
       └── exact CALLS ──> OrderService.ProcessOrder
  5. OrderService
       ├── DEPENDS_ON ──> IPaymentGateway
       └── exact CALLS ──> StripePaymentGateway.Charge (via ASP.NET Core DI mapping)
"""

import pytest
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.parsers.csharp.parser import CSharpParser
from archon.pipeline.resolution.imports import ModuleAndSymbolResolver
from archon.pipeline.resolution.dependency_resolver import DependencyAwareCallResolver
from archon.pipeline.resolution.endpoints import EndpointResolver


TSX_COMPONENT = """\
import { placeOrder } from './checkoutClient';

export function CheckoutButton() {
    async function handleClick() {
        await placeOrder({ id: '123' });
    }
}
"""

TS_API_CLIENT = """\
export async function placeOrder(data: any): Promise<any> {
    const response = await fetch('/api/v1/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    return response.json();
}
"""

CS_STARTUP = """\
namespace ArchonDemo
{
    public class Startup
    {
        public void ConfigureServices(IServiceCollection services)
        {
            services.AddScoped<IPaymentGateway, StripePaymentGateway>();
            services.AddScoped<IOrderService, OrderService>();
        }
    }
}
"""

CS_CONTROLLER = """\
namespace ArchonDemo.Controllers
{
    [ApiController]
    [Route("api/v1/orders")]
    public class OrderController : ControllerBase
    {
        private readonly OrderService orderService;

        public OrderController(OrderService orderService)
        {
            this.orderService = orderService;
        }

        [HttpPost("")]
        public IActionResult Checkout([FromBody] OrderRequest req)
        {
            this.orderService.ProcessOrder(req);
            return Ok();
        }
    }
}
"""

CS_SERVICE = """\
namespace ArchonDemo.Services
{
    public interface IPaymentGateway
    {
        void Charge(double amount);
    }

    public class StripePaymentGateway : IPaymentGateway
    {
        public void Charge(double amount)
        {
            // Implementation
        }
    }

    public class OrderService
    {
        private readonly IPaymentGateway gateway;

        public OrderService(IPaymentGateway gateway)
        {
            this.gateway = gateway;
        }

        public void ProcessOrder(OrderRequest req)
        {
            this.gateway.Charge(100.0);
        }
    }
}
"""


def test_full_live_polyglot_architecture_chain():
    """Verifies complete TS -> Endpoint -> C# Controller -> Service -> DI -> Gateway chain"""
    ts_p = TypeScriptParser()
    cs_p = CSharpParser()

    files = {
        "frontend/src/CheckoutButton.tsx": (ts_p, TSX_COMPONENT),
        "frontend/src/checkoutClient.ts": (ts_p, TS_API_CLIENT),
        "backend/Startup.cs": (cs_p, CS_STARTUP),
        "backend/OrderController.cs": (cs_p, CS_CONTROLLER),
        "backend/Services.cs": (cs_p, CS_SERVICE),
    }

    parsed_files = []
    file_contents = {}
    for path, (p, src) in files.items():
        pf = p.parse_file(path, src)
        parsed_files.append(pf)
        file_contents[path] = src

    # 1. Module & Symbol Resolver (ML-8)
    import_resolver = ModuleAndSymbolResolver()
    import_results = import_resolver.resolve(parsed_files, file_contents)

    # 2. Dependency-Aware Call Resolver (ML-10)
    dep_resolver = DependencyAwareCallResolver()
    dep_results = dep_resolver.resolve(parsed_files, file_contents)

    # 3. Endpoint Resolver (ML-4)
    ep_resolver = EndpointResolver()
    ep_results = ep_resolver.resolve(parsed_files, file_contents)

    all_results = import_results + dep_results + ep_results

    # ── Chain Link 1: TSX -> TS API client ──
    tsx_to_client_calls = [
        r for r in all_results
        if r.relationship == "CALLS" and "CheckoutButton" in r.source_id and "placeOrder" in r.target_id
    ]
    assert len(tsx_to_client_calls) >= 1, "Expected exact CALL from CheckoutButton -> placeOrder"

    # ── Chain Link 2: TS Client -> POST /api/v1/orders ──
    client_to_ep = [
        r for r in all_results
        if r.relationship == "REQUESTS" and "placeOrder" in r.source_id and "orders" in r.target_id
    ]
    assert len(client_to_ep) >= 1, "Expected REQUESTS edge to /api/v1/orders"

    # ── Chain Link 3: Endpoint -> OrderController.Checkout ──
    ep_to_controller = [
        r for r in all_results
        if r.relationship == "HANDLED_BY" and "orders" in r.source_id and "Checkout" in r.target_id
    ]
    assert len(ep_to_controller) >= 1, "Expected HANDLED_BY edge to OrderController.Checkout"

    # ── Chain Link 4: OrderController DEPENDS_ON OrderService ──
    controller_deps = [
        r for r in all_results
        if r.relationship == "DEPENDS_ON" and "OrderController" in r.source_id and "OrderService" in r.target_id
    ]
    assert len(controller_deps) >= 1, "Expected OrderController DEPENDS_ON OrderService"

    # ── Chain Link 5: OrderController.Checkout -> OrderService.ProcessOrder ──
    controller_calls = [
        r for r in all_results
        if r.relationship == "CALLS" and "Checkout" in r.source_id and "ProcessOrder" in r.target_id
    ]
    assert len(controller_calls) >= 1, "Expected OrderController.Checkout CALLS OrderService.ProcessOrder"

    # ── Chain Link 6: OrderService DEPENDS_ON IPaymentGateway ──
    service_deps = [
        r for r in all_results
        if r.relationship == "DEPENDS_ON" and "OrderService" in r.source_id and "IPaymentGateway" in r.target_id
    ]
    assert len(service_deps) >= 1, "Expected OrderService DEPENDS_ON IPaymentGateway"

    # ── Chain Link 7: OrderService.ProcessOrder -> StripePaymentGateway.Charge (via DI) ──
    service_calls = [
        r for r in all_results
        if r.relationship == "CALLS" and "ProcessOrder" in r.source_id and "StripePaymentGateway.Charge" in r.target_id
    ]
    assert len(service_calls) >= 1, "Expected OrderService.ProcessOrder CALLS StripePaymentGateway.Charge via DI binding"
    assert service_calls[0].resolution == "exact"
    assert service_calls[0].evidence_type == "dependency_injection_binding"
