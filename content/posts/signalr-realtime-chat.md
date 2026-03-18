---
title: "使用 SignalR 实现实时通信：聊天室完整实战"
date: 2026-01-15
draft: false
tags: ["signalr", "dotnet", "csharp", "realtime", "websocket", "react"]
categories: ["后端开发", "实时通信"]
description: "基于 .NET 6 + SignalR 实现完整聊天室功能，涵盖 Hub 设计、身份认证、在线用户列表、打字指示器、消息持久化与 React 客户端接入"
---

## SignalR 简介

SignalR 是微软开发的实时通信库，底层自动选择最优传输协议（WebSocket → Server-Sent Events → Long Polling），让服务端能主动推送消息给客户端，无需客户端轮询。

在 [SignalR-Simple-Demo](https://github.com/witeem/SignalR-Simple-Demo) 项目中，我实现了一个基于 .NET 6 + MVC + JavaScript 的聊天室。本文在此基础上进一步完善：加入身份认证、在线用户列表、打字指示器和消息持久化。

## 服务端实现

### 1. 消息与用户模型

```csharp
// Models/ChatMessage.cs
public record ChatMessage(
    string Id,
    string RoomName,
    string UserName,
    string Content,
    DateTime SentAt,
    MessageType Type = MessageType.Text
);

public enum MessageType { Text, System, Image }

// Models/OnlineUser.cs
public record OnlineUser(
    string ConnectionId,
    string UserName,
    string RoomName,
    DateTime JoinedAt
);
```

### 2. Hub 设计（完整版）

```csharp
// Hubs/ChatHub.cs
[Authorize] // 需要身份认证
public class ChatHub(IChatMessageRepository msgRepo, ILogger<ChatHub> logger)
    : Hub
{
    // 内存用户字典（生产环境应使用 Redis）
    private static readonly ConcurrentDictionary<string, OnlineUser> _onlineUsers = new();

    // ── 加入房间 ────────────────────────────────────────────────
    public async Task JoinRoom(string roomName)
    {
        var userName = Context.User!.Identity!.Name!;
        var user = new OnlineUser(Context.ConnectionId, userName, roomName, DateTime.UtcNow);
        _onlineUsers[Context.ConnectionId] = user;

        await Groups.AddToGroupAsync(Context.ConnectionId, roomName);

        // 推送历史消息（最近 50 条）
        var history = await msgRepo.GetRecentAsync(roomName, 50);
        await Clients.Caller.SendAsync("LoadHistory", history);

        // 通知房间内其他人
        await Clients.Group(roomName).SendAsync("UserJoined", new
        {
            userName,
            joinedAt = user.JoinedAt,
            onlineCount = GetRoomUserCount(roomName)
        });

        // 发送系统消息
        await SendSystemMessage(roomName, $"{userName} 加入了房间");
        logger.LogInformation("{User} joined room {Room}", userName, roomName);
    }

    // ── 离开房间 ────────────────────────────────────────────────
    public async Task LeaveRoom(string roomName)
    {
        await HandleUserLeft(roomName);
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, roomName);
    }

    // ── 发送消息 ────────────────────────────────────────────────
    public async Task SendMessage(string roomName, string content)
    {
        var userName = Context.User!.Identity!.Name!;

        // 内容过滤（XSS 防护）
        content = HtmlEncoder.Default.Encode(content.Trim());
        if (string.IsNullOrEmpty(content) || content.Length > 2000) return;

        var message = new ChatMessage(
            Id:       Guid.NewGuid().ToString("N"),
            RoomName: roomName,
            UserName: userName,
            Content:  content,
            SentAt:   DateTime.UtcNow
        );

        // 持久化到数据库
        await msgRepo.SaveAsync(message);

        // 广播给房间内所有人
        await Clients.Group(roomName).SendAsync("ReceiveMessage", message);
    }

    // ── 私聊 ─────────────────────────────────────────────────────
    public async Task SendPrivateMessage(string targetUserName, string content)
    {
        content = HtmlEncoder.Default.Encode(content.Trim());
        var senderName = Context.User!.Identity!.Name!;

        // 找到目标用户的所有连接（同一用户可能多设备在线）
        var targetConnections = _onlineUsers.Values
            .Where(u => u.UserName == targetUserName)
            .Select(u => u.ConnectionId)
            .ToList();

        if (!targetConnections.Any())
        {
            await Clients.Caller.SendAsync("Error", $"{targetUserName} 不在线");
            return;
        }

        var message = new ChatMessage(
            Id: Guid.NewGuid().ToString("N"),
            RoomName: "private",
            UserName: senderName,
            Content: content,
            SentAt: DateTime.UtcNow
        );

        // 同时发给对方和自己
        await Clients.Clients(targetConnections).SendAsync("ReceivePrivateMessage", message);
        await Clients.Caller.SendAsync("ReceivePrivateMessage", message);
    }

    // ── 打字指示器 ───────────────────────────────────────────────
    public async Task SendTyping(string roomName, bool isTyping)
    {
        var userName = Context.User!.Identity!.Name!;
        // 广播给房间内除自己以外的人
        await Clients.OthersInGroup(roomName).SendAsync("UserTyping", new
        {
            userName,
            isTyping
        });
    }

    // ── 获取在线用户列表 ─────────────────────────────────────────
    public Task<IEnumerable<string>> GetOnlineUsers(string roomName)
    {
        var users = _onlineUsers.Values
            .Where(u => u.RoomName == roomName)
            .Select(u => u.UserName)
            .Distinct();
        return Task.FromResult(users);
    }

    // ── 连接断开 ─────────────────────────────────────────────────
    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        if (_onlineUsers.TryRemove(Context.ConnectionId, out var user))
        {
            await HandleUserLeft(user.RoomName);
        }
        await base.OnDisconnectedAsync(exception);
    }

    // ── 私有方法 ─────────────────────────────────────────────────
    private async Task HandleUserLeft(string roomName)
    {
        var userName = Context.User?.Identity?.Name ?? "未知用户";
        await Clients.Group(roomName).SendAsync("UserLeft", new
        {
            userName,
            onlineCount = GetRoomUserCount(roomName) - 1
        });
        await SendSystemMessage(roomName, $"{userName} 离开了房间");
    }

    private async Task SendSystemMessage(string roomName, string content)
    {
        var sysMsg = new ChatMessage(
            Id: Guid.NewGuid().ToString("N"),
            RoomName: roomName,
            UserName: "系统",
            Content: content,
            SentAt: DateTime.UtcNow,
            Type: MessageType.System
        );
        await Clients.Group(roomName).SendAsync("ReceiveMessage", sysMsg);
    }

    private int GetRoomUserCount(string roomName)
        => _onlineUsers.Values.Count(u => u.RoomName == roomName);
}
```

### 3. 注册服务

```csharp
// Program.cs
builder.Services.AddSignalR(options =>
{
    options.EnableDetailedErrors      = builder.Environment.IsDevelopment();
    options.MaximumReceiveMessageSize = 102_400; // 100KB
    options.ClientTimeoutInterval     = TimeSpan.FromSeconds(60);
    options.KeepAliveInterval         = TimeSpan.FromSeconds(15);
    // 高频场景：开启 MessagePack 二进制协议，性能提升 30%+
    // .AddMessagePackProtocol();
});

// JWT 认证（Hub 上加了 [Authorize]）
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Events = new JwtBearerEvents
        {
            // SignalR 通过 QueryString 传递 Token
            OnMessageReceived = ctx =>
            {
                var token = ctx.Request.Query["access_token"];
                if (!string.IsNullOrEmpty(token) &&
                    ctx.HttpContext.Request.Path.StartsWithSegments("/chatHub"))
                {
                    ctx.Token = token;
                }
                return Task.CompletedTask;
            }
        };
        // ... TokenValidationParameters
    });

builder.Services.AddScoped<IChatMessageRepository, ChatMessageRepository>();

app.UseCors("SignalRPolicy");
app.UseAuthentication();
app.UseAuthorization();
app.MapHub<ChatHub>("/chatHub");
```

### 4. 消息持久化（EF Core）

```csharp
// Repositories/ChatMessageRepository.cs
public class ChatMessageRepository(AppDbContext db) : IChatMessageRepository
{
    public async Task SaveAsync(ChatMessage message)
    {
        db.ChatMessages.Add(new ChatMessageEntity
        {
            Id       = message.Id,
            RoomName = message.RoomName,
            UserName = message.UserName,
            Content  = message.Content,
            SentAt   = message.SentAt,
            Type     = (int)message.Type
        });
        await db.SaveChangesAsync();
    }

    public async Task<List<ChatMessage>> GetRecentAsync(string roomName, int count)
        => await db.ChatMessages
            .Where(m => m.RoomName == roomName)
            .OrderByDescending(m => m.SentAt)
            .Take(count)
            .OrderBy(m => m.SentAt)
            .Select(m => new ChatMessage(m.Id, m.RoomName, m.UserName, m.Content,
                m.SentAt, (MessageType)m.Type))
            .ToListAsync();
}
```

## React 客户端接入

### SignalR 服务封装

```typescript
// services/chatService.ts
import * as signalR from '@microsoft/signalr';

export type ChatMessage = {
  id:       string;
  userName: string;
  content:  string;
  sentAt:   string;
  type:     'Text' | 'System' | 'Image';
};

class ChatService {
  private connection: signalR.HubConnection | null = null;

  async connect(token: string): Promise<void> {
    this.connection = new signalR.HubConnectionBuilder()
      .withUrl('/chatHub', { accessTokenFactory: () => token })
      .withAutomaticReconnect({
        nextRetryDelayInMilliseconds: retryContext => {
          // 指数退避：0s, 2s, 5s, 10s, 30s...
          const delays = [0, 2000, 5000, 10000, 30000];
          return delays[Math.min(retryContext.previousRetryCount, delays.length - 1)];
        }
      })
      .configureLogging(signalR.LogLevel.Information)
      .build();

    await this.connection.start();
  }

  async joinRoom(roomName: string) {
    await this.connection?.invoke('JoinRoom', roomName);
  }

  async sendMessage(roomName: string, content: string) {
    await this.connection?.invoke('SendMessage', roomName, content);
  }

  async sendTyping(roomName: string, isTyping: boolean) {
    await this.connection?.invoke('SendTyping', roomName, isTyping);
  }

  onMessage(cb: (msg: ChatMessage) => void) {
    this.connection?.on('ReceiveMessage', cb);
  }

  onTyping(cb: (data: { userName: string; isTyping: boolean }) => void) {
    this.connection?.on('UserTyping', cb);
  }

  onReconnecting(cb: (error?: Error) => void) {
    this.connection?.onreconnecting(cb);
  }

  onReconnected(cb: (id?: string) => void) {
    this.connection?.onreconnected(cb);
  }

  async disconnect() {
    await this.connection?.stop();
  }
}

export const chatService = new ChatService();
```

### React 聊天室组件

```typescript
// components/ChatRoom.tsx
import { useEffect, useState, useRef, useCallback } from 'react';
import { chatService, type ChatMessage } from '../services/chatService';

export function ChatRoom({ roomName, token }: { roomName: string; token: string }) {
  const [messages, setMessages]         = useState<ChatMessage[]>([]);
  const [input, setInput]               = useState('');
  const [connected, setConnected]       = useState(false);
  const [typingUsers, setTypingUsers]   = useState<Set<string>>(new Set());
  const bottomRef                        = useRef<HTMLDivElement>(null);
  const typingTimerRef                   = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    chatService.connect(token).then(async () => {
      setConnected(true);
      await chatService.joinRoom(roomName);

      chatService.onMessage(msg =>
        setMessages(prev => [...prev, msg])
      );

      chatService.onTyping(({ userName, isTyping }) =>
        setTypingUsers(prev => {
          const next = new Set(prev);
          isTyping ? next.add(userName) : next.delete(userName);
          return next;
        })
      );
    });

    return () => { chatService.disconnect(); };
  }, [roomName, token]);

  // 新消息自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);
    // 防抖发送打字指示器
    clearTimeout(typingTimerRef.current);
    chatService.sendTyping(roomName, true);
    typingTimerRef.current = setTimeout(
      () => chatService.sendTyping(roomName, false),
      2000
    );
  }, [roomName]);

  const handleSend = useCallback(async () => {
    if (!input.trim()) return;
    clearTimeout(typingTimerRef.current);
    chatService.sendTyping(roomName, false);
    await chatService.sendMessage(roomName, input.trim());
    setInput('');
  }, [input, roomName]);

  return (
    <div className="chat-room">
      <div className="chat-status">
        <span className={`dot ${connected ? 'connected' : 'disconnected'}`} />
        {connected ? '已连接' : '连接中...'}
      </div>

      <div className="chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message message--${msg.type.toLowerCase()}`}>
            {msg.type !== 'System' && (
              <span className="message-user">{msg.userName}</span>
            )}
            <span className="message-content">{msg.content}</span>
            <span className="message-time">
              {new Date(msg.sentAt).toLocaleTimeString()}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {typingUsers.size > 0 && (
        <div className="typing-indicator">
          {[...typingUsers].join('、')} 正在输入...
        </div>
      )}

      <div className="chat-input">
        <input
          value={input}
          onChange={handleInput}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="输入消息，Enter 发送..."
          maxLength={2000}
        />
        <button onClick={handleSend} disabled={!connected || !input.trim()}>
          发送
        </button>
      </div>
    </div>
  );
}
```

## Scale Out：多实例部署（Redis Backplane）

单实例下消息广播正常，多实例时需要 Redis Backplane 打通：

```csharp
// 安装
// dotnet add package Microsoft.AspNetCore.SignalR.StackExchangeRedis

builder.Services.AddSignalR()
    .AddStackExchangeRedis(configuration["Redis:ConnectionString"]!, options =>
    {
        options.Configuration.ChannelPrefix = RedisChannel.Literal("ChatApp");
    });
```

架构示意：

```
Client A ──→ Instance 1 ──→ Redis Pub/Sub ──→ Instance 2 ──→ Client B
```

## 性能调优对比

| 配置项 | 默认值 | 高并发建议 |
|--------|--------|-----------|
| MaximumReceiveMessageSize | 32KB | 按业务设置，聊天场景 100KB |
| ClientTimeoutInterval | 30s | 60s（网络不稳定时） |
| KeepAliveInterval | 15s | 15–30s |
| 传输协议 | JSON | MessagePack（高频场景） |
| 持久化 | 可选 | Redis + 异步写库 |
| 多实例 | 不支持 | Redis Backplane |

## 总结

SignalR 极大地降低了实时通信的开发门槛，在 .NET 生态下几乎是最优的实时方案。无论是在线聊天、实时通知还是协作编辑，都可以快速实现。关键设计点：

1. **身份认证**：QueryString 传 Token，配合 `[Authorize]` 保护 Hub
2. **消息持久化**：入库后广播，断线重连后拉取历史记录
3. **打字指示器**：防抖 + `OthersInGroup` 精准推送
4. **私聊**：按用户名找所有连接，支持多设备
5. **Scale Out**：Redis Backplane 支持水平扩展

> 源码地址：[github.com/witeem/SignalR-Simple-Demo](https://github.com/witeem/SignalR-Simple-Demo)
