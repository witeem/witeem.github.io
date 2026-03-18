---
title: "深入理解 .NET Core 依赖注入 (DI) 机制"
date: 2026-03-10
draft: false
tags: ["dotnet", "csharp", "dependency-injection", "backend"]
categories: ["后端开发"]
description: "全面解析 .NET Core 内置依赖注入容器的原理、生命周期管理与最佳实践"
---

## 前言

依赖注入（Dependency Injection，DI）是 .NET Core 的核心设计原则之一，几乎贯穿了整个 ASP.NET Core 框架。本文将深入探讨其工作原理、三种生命周期的区别，以及在实际项目中的最佳实践。

## 什么是依赖注入？

依赖注入是控制反转（IoC）的一种实现方式。简单来说，不再由对象自己创建依赖，而是由外部容器在运行时注入。

```csharp
// ❌ 传统方式 - 强耦合
public class OrderService
{
    private readonly IRepository _repo = new SqlRepository(); // 直接 new
}

// ✅ 依赖注入 - 松耦合
public class OrderService
{
    private readonly IRepository _repo;

    public OrderService(IRepository repo) // 通过构造函数注入
    {
        _repo = repo;
    }
}
```

## 三种服务生命周期

.NET Core DI 提供了三种生命周期：

### 1. Singleton（单例）

整个应用程序生命周期内只创建一个实例。

```csharp
builder.Services.AddSingleton<IMyService, MyService>();
```

**适用场景**：配置管理、缓存服务、日志服务。

> ⚠️ 注意：Singleton 服务不应依赖 Scoped 或 Transient 服务。

### 2. Scoped（作用域）

每次 HTTP 请求创建一个实例，请求结束后销毁。

```csharp
builder.Services.AddScoped<IOrderService, OrderService>();
```

**适用场景**：数据库上下文（DbContext）、业务逻辑服务。

### 3. Transient（瞬态）

每次注入时都创建新实例。

```csharp
builder.Services.AddTransient<IEmailSender, EmailSender>();
```

**适用场景**：轻量级、无状态的服务。

## 实战：注册服务的几种方式

```csharp
var builder = WebApplication.CreateBuilder(args);

// 接口 + 实现类
builder.Services.AddScoped<IUserService, UserService>();

// 直接注册实现类
builder.Services.AddScoped<UserService>();

// 工厂方式（适合复杂初始化）
builder.Services.AddSingleton<IConfigService>(sp =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    return new ConfigService(config["AppKey"]!);
});

// 泛型服务注册
builder.Services.AddScoped(typeof(IRepository<>), typeof(SqlRepository<>));
```

## 避免常见陷阱

### Captive Dependency（捕获依赖）

```csharp
// ❌ 错误：Singleton 捕获了 Scoped 服务
public class MySingletonService
{
    public MySingletonService(IScopedService scoped) { } // 危险！
}

// ✅ 正确：使用 IServiceScopeFactory
public class MySingletonService
{
    private readonly IServiceScopeFactory _scopeFactory;

    public MySingletonService(IServiceScopeFactory scopeFactory)
    {
        _scopeFactory = scopeFactory;
    }

    public void DoWork()
    {
        using var scope = _scopeFactory.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<IScopedService>();
        // ...
    }
}
```

## SqlSugar 与 DI 集成示例

在 [BlogCore.API](https://github.com/witeem/BlogCore.API) 项目中，我将 SqlSugar 注册为 Scoped 服务：

```csharp
builder.Services.AddScoped<ISqlSugarClient>(sp =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    return new SqlSugarClient(new ConnectionConfig
    {
        ConnectionString = config.GetConnectionString("Default"),
        DbType = DbType.MySql,
        IsAutoCloseConnection = true
    });
});
```

## 总结

| 生命周期 | 创建时机 | 销毁时机 | 适用场景 |
|---------|---------|---------|---------|
| Singleton | 首次请求 | 应用关闭 | 配置、缓存 |
| Scoped | 每次请求 | 请求结束 | DbContext、业务服务 |
| Transient | 每次注入 | 作用域结束 | 无状态操作 |

依赖注入是构建可测试、可维护代码的基石。掌握好这三种生命周期，能有效避免内存泄漏和数据污染问题。
