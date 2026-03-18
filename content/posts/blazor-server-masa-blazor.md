---
title: "Blazor Server 实战：使用 MASA Blazor 构建现代化博客"
date: 2026-03-05
draft: false
tags: ["blazor", "csharp", "dotnet", "frontend", "masa-blazor"]
categories: ["前端开发", "Blazor"]
description: "从零开始用 Blazor Server + MASA Blazor 构建个人博客前端，涵盖组件开发、状态管理与服务集成"
---

## 为什么选择 Blazor？

作为一名 .NET 开发者，Blazor 让我可以用熟悉的 C# 语言开发现代化的 Web 前端。相比 React/Vue，它能共享后端的数据模型和业务逻辑代码，减少重复劳动。

[Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web) 是我基于 Blazor Server 开发的博客前端项目，UI 组件库采用了 MASA Blazor——一个基于 Material Design 规范、风格现代的 Blazor 组件库。

## 项目初始化

```bash
# 创建 Blazor Server 项目
dotnet new blazorserver -n Blazor-Blog-Web

# 添加 MASA Blazor
dotnet add package Masa.Blazor
```

在 `Program.cs` 中注册服务：

```csharp
builder.Services.AddMasaBlazor(options =>
{
    options.ConfigureTheme(theme =>
    {
        theme.Themes.Light.Primary = "#6366f1"; // 自定义主色
    });
});
```

## 核心页面结构

### 主布局 MainLayout.razor

```razor
@inherits LayoutComponentBase

<MApp>
    <MNavigationDrawer App Clipped>
        <BlogSidebar />
    </MNavigationDrawer>

    <MAppBar App Clipped Dense Elevation="1">
        <MAppBarNavIcon OnClick="ToggleDrawer" />
        <MToolbarTitle>Witeem's Blog</MToolbarTitle>
        <MSpacer />
        <MButton Href="/about" Text>关于我</MButton>
    </MAppBar>

    <MMain>
        <MContainer MaxWidth="MaxWidth.Large">
            @Body
        </MContainer>
    </MMain>
</MApp>
```

### 文章列表组件

```razor
@page "/posts"
@inject IPostService PostService

<MRow>
    @foreach (var post in posts)
    {
        <MCol Cols="12" Md="4">
            <MCard Hover>
                <MCardTitle>@post.Title</MCardTitle>
                <MCardSubtitle>@post.CreatedAt.ToString("yyyy-MM-dd")</MCardSubtitle>
                <MCardText>@post.Summary</MCardText>
                <MCardActions>
                    <MButton Text Color="primary" Href="@($"/posts/{post.Slug}")">
                        阅读更多 →
                    </MButton>
                </MCardActions>
            </MCard>
        </MCol>
    }
</MRow>

@code {
    private List<PostDto> posts = new();

    protected override async Task OnInitializedAsync()
    {
        posts = await PostService.GetPostsAsync();
    }
}
```

## 状态管理

Blazor Server 的状态天然保持在服务器端，通过注入 Scoped 服务来共享状态：

```csharp
// 用户状态服务
public class UserStateService
{
    public bool IsAuthenticated { get; private set; }
    public string? UserName { get; private set; }

    public event Action? OnChange;

    public void Login(string userName)
    {
        IsAuthenticated = true;
        UserName = userName;
        NotifyStateChanged();
    }

    private void NotifyStateChanged() => OnChange?.Invoke();
}
```

```razor
@inject UserStateService UserState
@implements IDisposable

@if (UserState.IsAuthenticated)
{
    <span>欢迎，@UserState.UserName</span>
}

@code {
    protected override void OnInitialized()
    {
        UserState.OnChange += StateHasChanged;
    }

    public void Dispose()
    {
        UserState.OnChange -= StateHasChanged;
    }
}
```

## Blazor vs React 对比

| 特性 | Blazor Server | React |
|------|--------------|-------|
| 语言 | C# | JavaScript/TypeScript |
| 运行方式 | WebSocket 实时同步 | 浏览器执行 JS |
| SEO | 良好（SSR） | 需要 Next.js 等 |
| 首屏速度 | 较慢（需建立 WS 连接） | 较快 |
| .NET 集成 | 原生 ✅ | 需要 API 调用 |
| 生态 | 成长中 | 非常成熟 |

## 总结

Blazor 对于 .NET 开发者来说是一个极具吸引力的选择，特别是在团队已有 C# 技术积累的情况下。MASA Blazor 提供了丰富的 Material Design 组件，让 UI 开发效率大幅提升。

> 源码地址：[github.com/witeem/Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web)
