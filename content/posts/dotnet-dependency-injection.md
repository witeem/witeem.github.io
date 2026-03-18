---
title: "深入理解 .NET Core 依赖注入 (DI) 机制"
date: 2026-03-10
draft: false
tags: ["dotnet", "csharp", "dependency-injection", "backend", "unit-test"]
categories: ["后端开发"]
description: "全面解析 .NET Core 内置依赖注入容器的原理、生命周期管理、高级注册模式、Keyed Services、单元测试与最佳实践"
---

## 前言

依赖注入（Dependency Injection，DI）是 .NET Core 的核心设计原则之一，几乎贯穿了整个 ASP.NET Core 框架。本文将深入探讨其工作原理、三种生命周期的区别、高级注册技巧，以及如何在单元测试中高效利用 DI。

## 什么是依赖注入？

依赖注入是控制反转（IoC）的一种实现方式。简单来说，不再由对象自己创建依赖，而是由外部容器在运行时注入。

```csharp
// ❌ 传统方式 - 强耦合，难以测试
public class OrderService
{
    private readonly IRepository _repo = new SqlRepository(); // 直接 new，无法替换
}

// ✅ 依赖注入 - 松耦合，易于测试和替换
public class OrderService
{
    private readonly IRepository _repo;

    public OrderService(IRepository repo) // 由容器注入
    {
        _repo = repo;
    }
}
```

## 三种服务生命周期

.NET Core DI 提供了三种生命周期，选错会导致数据污染或内存泄漏：

### 1. Singleton（单例）

整个应用程序生命周期内只创建**一个**实例，所有请求共享。

```csharp
builder.Services.AddSingleton<IMyService, MyService>();
builder.Services.AddSingleton<AppSettings>(); // 直接注册实现类
```

**适用场景**：配置管理、内存缓存、日志服务、连接池。

> ⚠️ **陷阱**：Singleton 服务不能直接依赖 Scoped 或 Transient 服务，否则会造成"捕获依赖"问题（见下文）。

### 2. Scoped（作用域）

每次 **HTTP 请求**创建一个实例，同一请求内共享，请求结束后销毁。

```csharp
builder.Services.AddScoped<IOrderService, OrderService>();
builder.Services.AddScoped<AppDbContext>(); // DbContext 必须是 Scoped
```

**适用场景**：数据库上下文（DbContext）、业务逻辑服务、当前用户上下文。

### 3. Transient（瞬态）

每次注入时都创建**新实例**，用完即抛。

```csharp
builder.Services.AddTransient<IEmailSender, SmtpEmailSender>();
builder.Services.AddTransient<IValidator<OrderDto>, OrderValidator>();
```

**适用场景**：轻量级、无状态的操作类，如验证器、格式化器。

### 生命周期对比

| 生命周期 | 创建时机 | 销毁时机 | 线程安全要求 | 典型场景 |
|---------|---------|---------|------------|---------|
| Singleton | 首次请求 | 应用关闭 | ✅ 必须线程安全 | 配置、缓存 |
| Scoped | 每次请求 | 请求结束 | 单请求内安全 | DbContext、业务服务 |
| Transient | 每次注入 | 作用域结束 | 无要求 | 无状态操作 |

## 注册服务的几种方式

```csharp
var builder = WebApplication.CreateBuilder(args);

// 1. 接口 + 实现类（最常见）
builder.Services.AddScoped<IUserService, UserService>();

// 2. 直接注册实现类（无接口）
builder.Services.AddScoped<UserService>();

// 3. 工厂方式（适合复杂初始化逻辑）
builder.Services.AddSingleton<IConfigService>(sp =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    return new ConfigService(config["AppKey"]!);
});

// 4. 开放泛型注册（一次注册所有泛型变体）
builder.Services.AddScoped(typeof(IRepository<>), typeof(SqlRepository<>));

// 5. 注册同一接口的多个实现（用于策略模式）
builder.Services.AddKeyedScoped<IPaymentGateway, AlipayGateway>("alipay");
builder.Services.AddKeyedScoped<IPaymentGateway, WechatPayGateway>("wechat");

// 6. TryAdd — 不会覆盖已注册的服务（适合库开发）
builder.Services.TryAddScoped<IMyService, DefaultMyService>();
```

## .NET 8 新特性：Keyed Services

.NET 8 正式引入了 **Keyed DI（键控依赖注入）**，完美解决多实现注入问题：

```csharp
// 注册
builder.Services.AddKeyedSingleton<ICacheService, RedisCacheService>("redis");
builder.Services.AddKeyedSingleton<ICacheService, MemoryCacheService>("memory");

// 构造函数注入
public class OrderService(
    [FromKeyedServices("redis")]  ICacheService redisCache,
    [FromKeyedServices("memory")] ICacheService memoryCache)
{
    // 精确获取 Redis 或内存缓存实现
}

// 手动解析
var redisCache = sp.GetRequiredKeyedService<ICacheService>("redis");
```

**之前的做法（.NET 7 及以下）**：

```csharp
// 使用工厂模式绕过，代码繁琐
builder.Services.AddSingleton<Func<string, ICacheService>>(sp => key =>
    key switch
    {
        "redis"  => sp.GetRequiredService<RedisCacheService>(),
        "memory" => sp.GetRequiredService<MemoryCacheService>(),
        _ => throw new ArgumentException($"未知缓存类型: {key}")
    });
```

## 避免常见陷阱

### ❌ Captive Dependency（捕获依赖）

```csharp
// ❌ 错误：Singleton 捕获了 Scoped 服务
// Scoped 服务会被"困死"在 Singleton 中，永远不会释放
public class MySingletonService
{
    public MySingletonService(IOrderService orderService) { } // 危险！
}

// ✅ 正确：通过 IServiceScopeFactory 手动创建作用域
public class MySingletonService(IServiceScopeFactory scopeFactory)
{
    public async Task ProcessAsync()
    {
        await using var scope = scopeFactory.CreateAsyncScope();
        var orderService = scope.ServiceProvider.GetRequiredService<IOrderService>();
        await orderService.ProcessAsync();
    } // scope 结束，Scoped 服务正常释放
}
```

### ❌ 在构造函数中执行异步操作

```csharp
// ❌ 错误：构造函数不能 await
public class DataService(IRepository repo)
{
    private readonly List<Item> _cache = repo.GetAllAsync().Result; // 死锁风险！
}

// ✅ 正确：使用 IHostedService 初始化
public class DataInitializer(IServiceScopeFactory factory) : IHostedService
{
    public async Task StartAsync(CancellationToken ct)
    {
        await using var scope = factory.CreateAsyncScope();
        var repo = scope.ServiceProvider.GetRequiredService<IRepository>();
        await repo.SeedAsync();
    }

    public Task StopAsync(CancellationToken ct) => Task.CompletedTask;
}
```

### ❌ 服务定位器反模式

```csharp
// ❌ 反模式：到处传递 IServiceProvider，掩盖真实依赖
public class BadService(IServiceProvider sp)
{
    public void Do() => sp.GetRequiredService<IOrderService>().Process();
}

// ✅ 正确：明确声明依赖
public class GoodService(IOrderService orderService)
{
    public void Do() => orderService.Process();
}
```

## SqlSugar 与 DI 集成

在 [BlogCore.API](https://github.com/witeem/BlogCore.API) 项目中，将 SqlSugar 注册为 Scoped 服务，配合工厂方式支持多租户：

```csharp
builder.Services.AddScoped<ISqlSugarClient>(sp =>
{
    var config  = sp.GetRequiredService<IConfiguration>();
    var logger  = sp.GetRequiredService<ILogger<SqlSugarClient>>();

    var client = new SqlSugarClient(new ConnectionConfig
    {
        ConnectionString      = config.GetConnectionString("Default"),
        DbType                = DbType.MySql,
        IsAutoCloseConnection = true,
        InitKeyType           = InitKeyType.Attribute
    });

    // SQL 执行日志
    client.Aop.OnLogExecuting = (sql, pars) =>
        logger.LogDebug("SQL: {Sql}", sql);

    return client;
});

// 泛型仓储
builder.Services.AddScoped(typeof(IBaseRepository<>), typeof(BaseRepository<>));
```

## 单元测试中的 DI

DI 让单元测试变得极为简单——只需替换真实依赖为 Mock：

```csharp
// 使用 Moq + xUnit
public class OrderServiceTests
{
    private readonly Mock<IRepository<Order>> _repoMock;
    private readonly Mock<IEmailSender>       _emailMock;
    private readonly OrderService              _sut;

    public OrderServiceTests()
    {
        _repoMock  = new Mock<IRepository<Order>>();
        _emailMock = new Mock<IEmailSender>();
        _sut = new OrderService(_repoMock.Object, _emailMock.Object);
    }

    [Fact]
    public async Task CreateOrder_ShouldSendConfirmationEmail()
    {
        // Arrange
        var dto = new CreateOrderDto { UserId = 1, Amount = 100 };
        _repoMock.Setup(r => r.AddAsync(It.IsAny<Order>()))
                 .ReturnsAsync(new Order { Id = 42 });

        // Act
        var result = await _sut.CreateAsync(dto);

        // Assert
        Assert.Equal(42, result.Id);
        _emailMock.Verify(e => e.SendAsync(
            It.Is<string>(s => s.Contains("42"))), Times.Once);
    }
}
```

### 集成测试：WebApplicationFactory

```csharp
public class OrderApiTests(WebApplicationFactory<Program> factory)
    : IClassFixture<WebApplicationFactory<Program>>
{
    [Fact]
    public async Task GetOrders_ReturnsOk()
    {
        // 替换真实数据库为内存数据库
        var client = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<AppDbContext>();
                services.AddDbContext<AppDbContext>(opt =>
                    opt.UseInMemoryDatabase("TestDb"));
            });
        }).CreateClient();

        var response = await client.GetAsync("/api/orders");
        response.EnsureSuccessStatusCode();
    }
}
```

## 装饰器模式与 DI

利用 DI 实现透明的行为增强（日志、缓存、重试）：

```csharp
// 核心实现
public class OrderService(IRepository<Order> repo) : IOrderService { ... }

// 缓存装饰器
public class CachedOrderService(IOrderService inner, IMemoryCache cache) : IOrderService
{
    public async Task<List<Order>> GetAllAsync()
        => await cache.GetOrCreateAsync("orders", _ => inner.GetAllAsync())!;
}

// 日志装饰器
public class LoggingOrderService(IOrderService inner, ILogger<LoggingOrderService> logger)
    : IOrderService
{
    public async Task<List<Order>> GetAllAsync()
    {
        logger.LogInformation("Fetching all orders");
        var result = await inner.GetAllAsync();
        logger.LogInformation("Fetched {Count} orders", result.Count);
        return result;
    }
}

// 注册：装饰链 OrderService → Cached → Logging
builder.Services.AddScoped<OrderService>();
builder.Services.AddScoped<IOrderService>(sp =>
    new LoggingOrderService(
        new CachedOrderService(
            sp.GetRequiredService<OrderService>(),
            sp.GetRequiredService<IMemoryCache>()),
        sp.GetRequiredService<ILogger<LoggingOrderService>>()));
```

## 总结

依赖注入是构建可测试、可维护代码的基石。掌握以下几个关键点，能有效避免内存泄漏和数据污染：

1. **分清三种生命周期**：Singleton 共享 → Scoped 请求 → Transient 每次
2. **警惕捕获依赖**：Singleton 不能直接依赖 Scoped，用 `IServiceScopeFactory` 解决
3. **善用 Keyed Services（.NET 8+）**：多实现场景的最优解
4. **拥抱装饰器模式**：透明地增加缓存、日志、重试等横切关注点
5. **面向接口编程**：接口抽象让单元测试轻松替换依赖

> 源码参考：[github.com/witeem/BlogCore.API](https://github.com/witeem/BlogCore.API)
