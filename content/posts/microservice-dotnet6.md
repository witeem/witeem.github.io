---
title: ".NET 6 微服务架构实践：从单体到微服务的演进"
date: 2026-02-20
draft: false
tags: ["microservices", "dotnet", "csharp", "architecture", "docker", "opentelemetry"]
categories: ["架构设计", "微服务"]
description: "基于 Microservice-Core-Template，深入讲解微服务架构的核心组件：服务注册发现、API 网关、消息总线、熔断降级、分布式事务与链路追踪"
---

## 背景

在 [Microservice-Core-Template](https://github.com/witeem/Microservice-Core-Template) 项目中，我实现了一个轻量级的 .NET 6 微服务架构模板。本文在原有基础上，进一步总结熔断降级、分布式追踪、配置中心等生产环境不可缺少的核心实践。

## 微服务核心组件全景

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (Ocelot/YARP)                │
│               限流 · 鉴权 · 负载均衡 · 路由               │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │   Service Discovery       │
         │   (Consul / Nacos)        │
         └─────────────┬─────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
   │ Order   │   │  User   │   │Product  │
   │ Service │   │ Service │   │ Service │
   └────┬────┘   └────┬────┘   └────┬────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
         ┌─────────────┴─────────────┐
         │   Message Bus             │
         │   (RabbitMQ / Kafka)      │
         └───────────────────────────┘
```

## 1. 服务注册与发现（Consul）

```csharp
// 服务注册
builder.Services.AddConsul(options =>
{
    options.Address = new Uri("http://consul:8500");
});

app.UseConsul(new AgentServiceRegistration
{
    ID      = $"order-service-{Guid.NewGuid()}",
    Name    = "order-service",
    Address = Environment.GetEnvironmentVariable("SERVICE_HOST") ?? "localhost",
    Port    = 5001,
    Tags    = new[] { "api", "v1" },
    Check   = new AgentServiceCheck
    {
        HTTP             = "http://localhost:5001/health",
        Interval         = TimeSpan.FromSeconds(10),
        Timeout          = TimeSpan.FromSeconds(5),
        DeregisterCriticalServiceAfter = TimeSpan.FromMinutes(1)
    }
});
```

健康检查端点：

```csharp
// 添加详细健康检查（数据库、Redis、外部依赖）
builder.Services.AddHealthChecks()
    .AddMySql(connectionString, name: "mysql")
    .AddRedis(redisConnection, name: "redis")
    .AddUrlGroup(new Uri("http://user-service/health"), name: "user-service");

app.MapHealthChecks("/health", new HealthCheckOptions
{
    ResponseWriter = UIResponseWriter.WriteHealthCheckUIResponse
});
```

## 2. API 网关（Ocelot + Consul）

```json
// ocelot.json
{
  "Routes": [
    {
      "DownstreamPathTemplate": "/api/{everything}",
      "DownstreamScheme": "http",
      "ServiceName": "order-service",
      "LoadBalancerOptions": { "Type": "RoundRobin" },
      "UpstreamPathTemplate": "/order/{everything}",
      "UpstreamHttpMethod": ["GET", "POST", "PUT", "DELETE"],
      "RateLimitOptions": {
        "EnableRateLimiting": true,
        "Period": "1m",
        "Limit": 100
      },
      "QoSOptions": {
        "ExceptionsAllowedBeforeBreaking": 3,
        "DurationOfBreak": 10000,
        "TimeoutValue": 5000
      }
    }
  ],
  "GlobalConfiguration": {
    "ServiceDiscoveryProvider": {
      "Scheme": "http",
      "Host": "consul",
      "Port": 8500,
      "Type": "Consul"
    },
    "RateLimitOptions": {
      "DisableRateLimitHeaders": false,
      "QuotaExceededMessage": "请求过于频繁，请稍后重试"
    }
  }
}
```

## 3. 统一 JWT 鉴权

```csharp
// 在网关层统一验证 Token，下游服务无需重复鉴权
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer           = true,
            ValidIssuer              = configuration["JWT:Issuer"],
            ValidateAudience         = true,
            ValidAudience            = configuration["JWT:Audience"],
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(configuration["JWT:SecretKey"]!)),
            ClockSkew = TimeSpan.FromSeconds(30)
        };
    });
```

## 4. 熔断降级（Polly）

生产环境必须为所有外部调用加上熔断、重试、超时策略：

```csharp
// 使用 Polly v8（.NET 8 推荐）
builder.Services.AddHttpClient<IOrderServiceClient, OrderServiceClient>()
    .AddResilienceHandler("order-pipeline", builder =>
    {
        // 重试：最多 3 次，指数退避
        builder.AddRetry(new HttpRetryStrategyOptions
        {
            MaxRetryAttempts = 3,
            Delay = TimeSpan.FromMilliseconds(200),
            BackoffType = DelayBackoffType.Exponential,
            ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
                .HandleResult(r => r.StatusCode >= HttpStatusCode.InternalServerError)
        });

        // 熔断：连续 5 次失败则熔断 30 秒
        builder.AddCircuitBreaker(new HttpCircuitBreakerStrategyOptions
        {
            FailureRatio = 0.5,
            MinimumThroughput = 10,
            SamplingDuration = TimeSpan.FromSeconds(30),
            BreakDuration = TimeSpan.FromSeconds(30)
        });

        // 超时：单次调用最长 5 秒
        builder.AddTimeout(TimeSpan.FromSeconds(5));
    });
```

降级回调（Fallback）：

```csharp
public class OrderServiceClient(HttpClient http, ILogger<OrderServiceClient> logger)
    : IOrderServiceClient
{
    public async Task<List<OrderDto>> GetOrdersAsync(int userId)
    {
        try
        {
            return await http.GetFromJsonAsync<List<OrderDto>>($"/api/orders/{userId}")
                   ?? [];
        }
        catch (BrokenCircuitException)
        {
            logger.LogWarning("订单服务熔断，返回降级数据");
            return []; // 降级：返回空列表或缓存数据
        }
    }
}
```

## 5. 服务间通信

### 同步通信（HTTP + gRPC）

```csharp
// HTTP + HttpClientFactory + 服务发现
builder.Services.AddHttpClient("user-service", client =>
{
    client.BaseAddress = new Uri("http://user-service");
    client.Timeout = TimeSpan.FromSeconds(5);
});

// gRPC（高性能场景推荐）
builder.Services.AddGrpcClient<UserService.UserServiceClient>(options =>
{
    options.Address = new Uri("http://user-service:5002");
});
```

### 异步通信（RabbitMQ + MassTransit）

```csharp
// 事件定义
public record OrderCreatedEvent(int OrderId, int UserId, decimal TotalAmount);

// 发布事件（订单服务）
builder.Services.AddMassTransit(x =>
{
    x.UsingRabbitMq((ctx, cfg) =>
    {
        cfg.Host("rabbitmq://rabbitmq", h =>
        {
            h.Username("guest");
            h.Password("guest");
        });
        cfg.ConfigureEndpoints(ctx);
    });
});

// 消费事件（通知服务）
public class OrderCreatedConsumer(IEmailSender email)
    : IConsumer<OrderCreatedEvent>
{
    public async Task Consume(ConsumeContext<OrderCreatedEvent> context)
    {
        var evt = context.Message;
        await email.SendAsync(
            subject: $"订单 #{evt.OrderId} 已创建",
            body: $"金额：{evt.TotalAmount:C}");
    }
}
```

## 6. 分布式事务（Saga 模式）

微服务不能共用数据库，跨服务事务用 **Saga** 编排：

```csharp
// 使用 MassTransit Saga StateMachine
public class OrderStateMachine : MassTransitStateMachine<OrderSaga>
{
    public State Submitted  { get; private set; } = null!;
    public State Paid       { get; private set; } = null!;
    public State Shipped    { get; private set; } = null!;
    public State Cancelled  { get; private set; } = null!;

    public Event<OrderSubmittedEvent>  OrderSubmitted  { get; private set; } = null!;
    public Event<PaymentCompletedEvent> PaymentCompleted { get; private set; } = null!;
    public Event<PaymentFailedEvent>   PaymentFailed   { get; private set; } = null!;

    public OrderStateMachine()
    {
        InstanceState(x => x.CurrentState);

        Event(() => OrderSubmitted,  x => x.CorrelateById(m => m.Message.OrderId));
        Event(() => PaymentCompleted, x => x.CorrelateById(m => m.Message.OrderId));
        Event(() => PaymentFailed,   x => x.CorrelateById(m => m.Message.OrderId));

        Initially(
            When(OrderSubmitted)
                .Then(ctx => ctx.Saga.UserId = ctx.Message.UserId)
                .PublishAsync(ctx => ctx.Init<ProcessPaymentCommand>(new
                {
                    ctx.Message.OrderId, ctx.Message.Amount
                }))
                .TransitionTo(Submitted));

        During(Submitted,
            When(PaymentCompleted).TransitionTo(Paid),
            When(PaymentFailed)
                .PublishAsync(ctx => ctx.Init<CancelOrderCommand>(new
                {
                    ctx.Message.OrderId, Reason = "支付失败"
                }))
                .TransitionTo(Cancelled));
    }
}
```

## 7. 链路追踪（OpenTelemetry）

分布式系统必须有追踪才能排查跨服务问题：

```csharp
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .AddAspNetCoreInstrumentation()
            .AddHttpClientInstrumentation()
            .AddEntityFrameworkCoreInstrumentation()
            .AddSource("OrderService")
            .AddOtlpExporter(opt =>
            {
                opt.Endpoint = new Uri("http://jaeger:4317");
            });
    })
    .WithMetrics(metrics =>
    {
        metrics
            .AddAspNetCoreInstrumentation()
            .AddRuntimeInstrumentation()
            .AddPrometheusExporter(); // Prometheus 抓取
    });

// 自定义 Span
private static readonly ActivitySource _activitySource = new("OrderService");

public async Task<Order> CreateAsync(CreateOrderDto dto)
{
    using var activity = _activitySource.StartActivity("CreateOrder");
    activity?.SetTag("order.userId", dto.UserId);
    activity?.SetTag("order.amount", dto.Amount);

    var order = await _repo.AddAsync(new Order { ... });
    activity?.SetTag("order.id", order.Id);
    return order;
}
```

## 8. Docker Compose 编排

```yaml
version: '3.8'

services:
  consul:
    image: consul:1.15
    ports: ["8500:8500"]
    command: consul agent -dev -client=0.0.0.0

  api-gateway:
    build: ./Gateway
    ports: ["5000:80"]
    depends_on: [consul]
    environment:
      - ASPNETCORE_ENVIRONMENT=Production

  order-service:
    build: ./Services/OrderService
    environment:
      - CONSUL_HOST=consul
      - ConnectionStrings__Default=Server=mysql;Database=orders;...
    depends_on: [consul, mysql]
    deploy:
      replicas: 2  # 水平扩展

  user-service:
    build: ./Services/UserService
    depends_on: [consul, mysql]

  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["16686:16686", "4317:4317"]

  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

volumes:
  mysql_data:
```

## 最佳实践总结

| 关注点 | 实践建议 |
|--------|---------|
| **单一职责** | 每个微服务只负责一个业务领域 |
| **数据隔离** | 每个服务拥有独立数据库，禁止跨库 Join |
| **异步优先** | 服务间尽量用消息队列解耦，降低时间耦合 |
| **幂等设计** | 消息消费、API 调用必须是幂等的 |
| **熔断降级** | 所有外部调用必须加 Polly 策略 |
| **健康检查** | 每个服务必须暴露 `/health` 端点 |
| **链路追踪** | 集成 OpenTelemetry + Jaeger 追踪跨服务请求 |
| **配置外置** | 配置放 Consul KV 或 Nacos，不要写死在代码里 |
| **独立部署** | 每个服务有独立的 CI/CD 流水线 |

> ⚠️ **微服务不是银弹**：只有当团队规模超过 10 人、业务模块明确、需要独立扩展时才值得引入。过早拆分只会增加运维负担。

> 源码地址：[github.com/witeem/Microservice-Core-Template](https://github.com/witeem/Microservice-Core-Template)
