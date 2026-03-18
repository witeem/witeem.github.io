---
title: ".NET 6 微服务架构实践：从单体到微服务的演进"
date: 2026-02-20
draft: false
tags: ["microservices", "dotnet", "csharp", "architecture", "docker"]
categories: ["架构设计", "微服务"]
description: "基于 Microservice-Core-Template 项目，讲解微服务架构的核心组件：服务注册发现、API 网关、消息总线的设计与实现"
---

## 背景

在 [Microservice-Core-Template](https://github.com/witeem/Microservice-Core-Template) 项目中，我实现了一个轻量级的 .NET 6 微服务架构模板。本文总结其核心设计思路。

## 微服务核心组件

```
┌─────────────────────────────────────────────────┐
│                   API Gateway                    │
│              (Ocelot / YARP)                    │
└──────────────┬──────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    │   Service Discovery │
    │    (Consul / Nacos) │
    └──────────┬──────────┘
               │
   ┌───────────┼───────────┐
   │           │           │
┌──┴──┐    ┌──┴──┐    ┌──┴──┐
│ SVC │    │ SVC │    │ SVC │
│  A  │    │  B  │    │  C  │
└─────┘    └─────┘    └─────┘
```

## 1. 服务注册与发现（Consul）

```csharp
// 服务注册
builder.Services.AddConsul(options =>
{
    options.Address = new Uri("http://consul:8500");
});

// 在 Program.cs 中注册服务
app.UseConsul(new AgentServiceRegistration
{
    ID = $"order-service-{Guid.NewGuid()}",
    Name = "order-service",
    Address = "localhost",
    Port = 5001,
    Tags = new[] { "api", "v1" },
    Check = new AgentServiceCheck
    {
        HTTP = "http://localhost:5001/health",
        Interval = TimeSpan.FromSeconds(10),
        Timeout = TimeSpan.FromSeconds(5)
    }
});
```

## 2. API 网关配置（Ocelot）

```json
// ocelot.json
{
  "Routes": [
    {
      "DownstreamPathTemplate": "/api/{everything}",
      "DownstreamScheme": "http",
      "DownstreamHostAndPorts": [],
      "ServiceName": "order-service",
      "LoadBalancerOptions": {
        "Type": "RoundRobin"
      },
      "UpstreamPathTemplate": "/order/{everything}",
      "UpstreamHttpMethod": ["GET", "POST", "PUT", "DELETE"]
    }
  ],
  "GlobalConfiguration": {
    "ServiceDiscoveryProvider": {
      "Scheme": "http",
      "Host": "consul",
      "Port": 8500,
      "Type": "Consul"
    }
  }
}
```

```csharp
// Program.cs
builder.Configuration.AddJsonFile("ocelot.json");
builder.Services.AddOcelot().AddConsul();
app.UseOcelot().Wait();
```

## 3. 统一 JWT 鉴权

```csharp
// 在网关层统一验证 Token
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = configuration["JWT:Issuer"],
            ValidateAudience = true,
            ValidAudience = configuration["JWT:Audience"],
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(configuration["JWT:SecretKey"]!))
        };
    });
```

## 4. Docker Compose 编排

```yaml
version: '3.8'

services:
  consul:
    image: consul:latest
    ports:
      - "8500:8500"

  api-gateway:
    build: ./Gateway
    ports:
      - "5000:80"
    depends_on:
      - consul

  order-service:
    build: ./Services/OrderService
    environment:
      - CONSUL_HOST=consul
    depends_on:
      - consul
    deploy:
      replicas: 2  # 水平扩展

  user-service:
    build: ./Services/UserService
    environment:
      - CONSUL_HOST=consul
    depends_on:
      - consul

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

## 服务间通信

### 同步通信（HTTP/gRPC）

```csharp
// 使用 HttpClientFactory + 服务发现
builder.Services.AddHttpClient("order-service", client =>
{
    client.BaseAddress = new Uri("http://order-service");
});

// 或使用 gRPC
builder.Services.AddGrpcClient<OrderService.OrderServiceClient>(options =>
{
    options.Address = new Uri("http://order-service");
});
```

### 异步通信（消息总线）

```csharp
// 使用 RabbitMQ + MassTransit
builder.Services.AddMassTransit(x =>
{
    x.AddConsumer<OrderCreatedConsumer>();

    x.UsingRabbitMq((ctx, cfg) =>
    {
        cfg.Host("rabbitmq://localhost");
        cfg.ConfigureEndpoints(ctx);
    });
});

// 发布事件
await _publishEndpoint.Publish(new OrderCreatedEvent
{
    OrderId = order.Id,
    UserId = order.UserId,
    TotalAmount = order.Total
});
```

## 最佳实践总结

1. **单一职责**：每个微服务只负责一个业务领域
2. **独立部署**：每个服务有独立的 CI/CD 流水线
3. **数据隔离**：每个服务拥有独立的数据库
4. **幂等设计**：消息消费必须是幂等的
5. **健康检查**：所有服务必须暴露 `/health` 端点
6. **链路追踪**：集成 OpenTelemetry 进行分布式追踪

微服务不是银弹，只有当团队规模和业务复杂度达到一定程度时才值得引入。

> 源码地址：[github.com/witeem/Microservice-Core-Template](https://github.com/witeem/Microservice-Core-Template)
