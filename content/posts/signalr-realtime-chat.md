---
title: "使用 SignalR 实现实时通信：聊天室完整实战"
date: 2026-01-15
draft: false
tags: ["signalr", "dotnet", "csharp", "realtime", "websocket"]
categories: ["后端开发", "实时通信"]
description: "基于 .NET 6 + SignalR + JavaScript 实现完整聊天室功能，包括 Hub 设计、断线重连、消息广播等核心机制"
---

## SignalR 简介

SignalR 是微软开发的实时通信库，底层自动选择最优传输协议（WebSocket → Server-Sent Events → Long Polling），让服务端能主动推送消息给客户端。

在 [SignalR-Simple-Demo](https://github.com/witeem/SignalR-Simple-Demo) 项目中，我实现了一个基于 .NET 6 + MVC + JavaScript 的聊天室。

## 服务端实现

### 1. 创建 Hub

```csharp
// Hubs/ChatHub.cs
using Microsoft.AspNetCore.SignalR;

public class ChatHub : Hub
{
    private static readonly Dictionary<string, string> _users = new();

    // 用户加入
    public async Task JoinRoom(string userName, string roomName)
    {
        _users[Context.ConnectionId] = userName;
        await Groups.AddToGroupAsync(Context.ConnectionId, roomName);

        await Clients.Group(roomName).SendAsync("ReceiveMessage", "系统",
            $"{userName} 加入了房间");
    }

    // 发送消息
    public async Task SendMessage(string roomName, string message)
    {
        var userName = _users.GetValueOrDefault(Context.ConnectionId, "匿名");
        await Clients.Group(roomName).SendAsync("ReceiveMessage", userName, message);
    }

    // 私聊
    public async Task SendPrivateMessage(string targetConnectionId, string message)
    {
        var senderName = _users.GetValueOrDefault(Context.ConnectionId, "匿名");
        await Clients.Client(targetConnectionId).SendAsync(
            "ReceivePrivateMessage", senderName, message);
    }

    // 用户断开连接
    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        if (_users.TryGetValue(Context.ConnectionId, out var userName))
        {
            _users.Remove(Context.ConnectionId);
            await Clients.All.SendAsync("ReceiveMessage", "系统", $"{userName} 离开了");
        }
        await base.OnDisconnectedAsync(exception);
    }
}
```

### 2. 注册服务

```csharp
// Program.cs
builder.Services.AddSignalR(options =>
{
    options.EnableDetailedErrors = builder.Environment.IsDevelopment();
    options.MaximumReceiveMessageSize = 102400; // 100KB
    options.ClientTimeoutInterval = TimeSpan.FromSeconds(30);
    options.KeepAliveInterval = TimeSpan.FromSeconds(15);
});

// 配置跨域（开发环境）
builder.Services.AddCors(options =>
{
    options.AddPolicy("SignalRPolicy", policy =>
    {
        policy.WithOrigins("http://localhost:3000")
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials();
    });
});

app.UseCors("SignalRPolicy");
app.MapHub<ChatHub>("/chatHub");
```

## 客户端实现（JavaScript）

```javascript
// chat.js
const connection = new signalR.HubConnectionBuilder()
    .withUrl("/chatHub")
    .withAutomaticReconnect([0, 2000, 5000, 10000, 30000]) // 断线重连策略
    .configureLogging(signalR.LogLevel.Information)
    .build();

// 监听消息
connection.on("ReceiveMessage", (userName, message) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${escapeHtml(userName)}</strong>: ${escapeHtml(message)}`;
    document.getElementById("messageList").appendChild(li);
});

// 连接状态监听
connection.onreconnecting(error => {
    console.log(`连接中断，尝试重连... ${error}`);
    updateStatus('reconnecting');
});

connection.onreconnected(connectionId => {
    console.log(`已重新连接: ${connectionId}`);
    updateStatus('connected');
});

connection.onclose(error => {
    console.log(`连接已关闭: ${error}`);
    updateStatus('disconnected');
});

// 启动连接
async function startConnection() {
    try {
        await connection.start();
        console.log("SignalR 连接成功");
        await connection.invoke("JoinRoom", userName, roomName);
    } catch (err) {
        console.error(err);
        setTimeout(startConnection, 5000);
    }
}

// 发送消息
async function sendMessage() {
    const message = document.getElementById("messageInput").value;
    if (!message.trim()) return;

    try {
        await connection.invoke("SendMessage", roomName, message);
        document.getElementById("messageInput").value = "";
    } catch (err) {
        console.error(err);
    }
}

startConnection();
```

## 扩展场景：Scale Out

当需要多实例部署时，使用 Redis Backplane：

```csharp
// 安装包
// dotnet add package Microsoft.AspNetCore.SignalR.StackExchangeRedis

builder.Services.AddSignalR()
    .AddStackExchangeRedis("localhost:6379", options =>
    {
        options.Configuration.ChannelPrefix = "MyApp";
    });
```

## 性能调优建议

| 配置项 | 默认值 | 建议 |
|--------|--------|------|
| MaximumReceiveMessageSize | 32KB | 根据业务调整 |
| ClientTimeoutInterval | 30s | 生产环境可调高 |
| KeepAliveInterval | 15s | 心跳保持连接 |
| MessagePackProtocol | 未启用 | 高频场景开启二进制协议 |

## 总结

SignalR 极大地降低了实时通信的开发门槛，在 .NET 生态下几乎是最优的实时方案。无论是在线聊天、实时通知还是协作编辑，都可以快速实现。

> 源码地址：[github.com/witeem/SignalR-Simple-Demo](https://github.com/witeem/SignalR-Simple-Demo)
