---
title: "Blazor Server 实战：使用 MASA Blazor 构建现代化博客"
date: 2026-03-05
draft: false
tags: ["blazor", "csharp", "dotnet", "frontend", "masa-blazor"]
categories: ["前端开发", "Blazor"]
description: "从零开始用 Blazor Server + MASA Blazor 构建个人博客前端，涵盖组件通信、状态管理、表单验证、性能优化与生产部署完整实践"
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

在 ``Program.cs`` 中注册服务：

```csharp
builder.Services.AddMasaBlazor(options =>
{
    options.ConfigureTheme(theme =>
    {
        theme.Themes.Light.Primary   = "#0084FF"; // 知乎蓝
        theme.Themes.Light.Secondary = "#00AAFF";
        theme.Themes.Dark.Primary    = "#66B5FF";
    });
});
```

## 核心页面结构

### 主布局 MainLayout.razor

```razor
@inherits LayoutComponentBase

<MApp>
    <MNavigationDrawer App Clipped @bind-Value="drawerOpen">
        <BlogSidebar />
    </MNavigationDrawer>

    <MAppBar App Clipped Dense Elevation="1">
        <MAppBarNavIcon OnClick="@(() => drawerOpen = !drawerOpen)" />
        <MToolbarTitle>Witeem s Blog</MToolbarTitle>
        <MSpacer />
        <MButton Href="/posts" Text>文章</MButton>
        <MButton Href="/tags"  Text>标签</MButton>
        <MButton Href="/about" Text>关于我</MButton>
    </MAppBar>

    <MMain>
        <MContainer MaxWidth="MaxWidth.Large">
            @Body
        </MContainer>
    </MMain>

    <MFooter App>
        <span>2026 Witeem s Blog Built with Blazor + MASA Blazor</span>
    </MFooter>
</MApp>

@code {
    private bool drawerOpen = true;
}
```

### 文章列表组件

```razor
@page "/posts"
@inject IPostService PostService

@if (loading)
{
    <div class="d-flex justify-center mt-8">
        <MProgressCircular Indeterminate Color="primary" Size="48" />
    </div>
}
else
{
    <MRow>
        @foreach (var post in posts)
        {
            <MCol Cols="12" Md="4">
                <MCard Hover Class="mb-4" Elevation="2">
                    <MCardTitle>@post.Title</MCardTitle>
                    <MCardSubtitle>
                        <MIcon Small Class="mr-1">mdi-calendar</MIcon>
                        @post.CreatedAt.ToString("yyyy-MM-dd")
                    </MCardSubtitle>
                    <MCardText>@post.Summary</MCardText>
                    <MCardActions>
                        @foreach (var tag in post.Tags.Take(3))
                        {
                            <MChip Small Color="primary" Outlined Class="mr-1">@tag</MChip>
                        }
                        <MSpacer />
                        <MButton Text Color="primary" Href="@($"/posts/{post.Slug}")">
                            阅读更多
                        </MButton>
                    </MCardActions>
                </MCard>
            </MCol>
        }
    </MRow>
}

@code {
    private List<PostDto> posts = new();
    private bool loading = true;

    protected override async Task OnInitializedAsync()
    {
        posts = await PostService.GetPostsAsync();
        loading = false;
    }
}
```

## 组件通信模式

### 1. EventCallback 父子通信

```razor
<!-- 子组件 SearchBar.razor -->
<MTextField @bind-Value="keyword"
            Placeholder="搜索文章..."
            Clearable
            PrependInnerIcon="mdi-magnify"
            OnKeyUp="OnKeyUp" />

@code {
    [Parameter] public EventCallback<string> OnSearch { get; set; }
    private string keyword = string.Empty;

    private async Task OnKeyUp(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
            await OnSearch.InvokeAsync(keyword);
    }
}

<!-- 父组件调用 -->
<SearchBar OnSearch="HandleSearch" />

@code {
    private async Task HandleSearch(string keyword)
    {
        posts = await PostService.SearchAsync(keyword);
    }
}
```

### 2. CascadingValue 跨层数据传递

```razor
<!-- App.razor 根组件：向全局广播当前用户 -->
<CascadingValue Value="@currentUser">
    <Router AppAssembly="@typeof(App).Assembly">
        <Found Context="routeData">
            <RouteView RouteData="@routeData" DefaultLayout="@typeof(MainLayout)" />
        </Found>
    </Router>
</CascadingValue>

@code {
    private UserInfo? currentUser;

    protected override async Task OnInitializedAsync()
        => currentUser = await AuthService.GetCurrentUserAsync();
}

<!-- 任意深层子组件直接消费 -->
@code {
    [CascadingParameter] private UserInfo? CurrentUser { get; set; }
}
```

### 3. 全局状态服务

```csharp
// Services/UserStateService.cs
public class UserStateService
{
    public bool IsAuthenticated { get; private set; }
    public string? UserName    { get; private set; }
    public string? AvatarUrl   { get; private set; }

    public event Action? OnChange;

    public void Login(string userName, string avatarUrl = "")
    {
        IsAuthenticated = true;
        UserName  = userName;
        AvatarUrl = avatarUrl;
        NotifyStateChanged();
    }

    public void Logout()
    {
        IsAuthenticated = false;
        UserName = AvatarUrl = null;
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
    <div class="d-flex align-center gap-2">
        <MAvatar Size="32">
            <MImage Src="@UserState.AvatarUrl" Alt="@UserState.UserName" />
        </MAvatar>
        <span>欢迎，@UserState.UserName</span>
        <MButton Text Small OnClick="Logout">退出</MButton>
    </div>
}
else
{
    <MButton Color="primary" Href="/login">登录</MButton>
}

@code {
    protected override void OnInitialized()
        => UserState.OnChange += StateHasChanged;

    private async Task Logout()
    {
        await AuthService.LogoutAsync();
        UserState.Logout();
        Navigation.NavigateTo("/");
    }

    public void Dispose()
        => UserState.OnChange -= StateHasChanged;
}
```

## 表单验证

```csharp
// Models/ContactForm.cs
public class ContactForm
{
    [Required(ErrorMessage = "姓名不能为空")]
    [StringLength(50, ErrorMessage = "姓名不超过 50 个字符")]
    public string Name { get; set; } = string.Empty;

    [Required(ErrorMessage = "邮箱不能为空")]
    [EmailAddress(ErrorMessage = "请输入有效的邮箱地址")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "内容不能为空")]
    [MinLength(10, ErrorMessage = "内容至少 10 个字符")]
    public string Message { get; set; } = string.Empty;
}
```

```razor
@page "/contact"

<EditForm Model="@form" OnValidSubmit="HandleSubmit">
    <DataAnnotationsValidator />
    <MForm>
        <MTextField Label="姓名"    @bind-Value="form.Name"    For="@(() => form.Name)"    Outlined />
        <MTextField Label="邮箱"    @bind-Value="form.Email"   For="@(() => form.Email)"   Outlined Type="email" />
        <MTextarea  Label="留言内容" @bind-Value="form.Message" For="@(() => form.Message)" Outlined Rows="5" />
        <MButton Type="submit" Color="primary" Loading="@submitting" Block>发送留言</MButton>
    </MForm>
</EditForm>

@code {
    private ContactForm form = new();
    private bool submitting = false;

    private async Task HandleSubmit()
    {
        submitting = true;
        await ContactService.SendAsync(form);
        submitting = false;
        Snackbar.Add("留言发送成功！", Severity.Success);
        form = new();
    }
}
```

## 性能优化

### 1. Virtualize 虚拟列表

```razor
<Virtualize Items="@allPosts" Context="post" OverscanCount="5">
    <MCard Class="mb-3" Outlined>
        <MCardTitle>@post.Title</MCardTitle>
        <MCardSubtitle>@post.CreatedAt.ToString("yyyy-MM-dd")</MCardSubtitle>
    </MCard>
</Virtualize>
```

### 2. ShouldRender 精细控制重渲染

```razor
@code {
    private int _lastCount = 0;

    protected override bool ShouldRender()
    {
        if (posts.Count == _lastCount) return false;
        _lastCount = posts.Count;
        return true;
    }
}
```

### 3. 内存缓存装饰器

```csharp
public class CachedPostService(IPostService inner, IMemoryCache cache) : IPostService
{
    public async Task<List<PostDto>> GetPostsAsync()
        => await cache.GetOrCreateAsync("posts:all", async entry =>
        {
            entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            return await inner.GetPostsAsync();
        }) ?? [];
}

// Program.cs
builder.Services.AddScoped<PostService>();
builder.Services.AddScoped<IPostService>(sp =>
    new CachedPostService(
        sp.GetRequiredService<PostService>(),
        sp.GetRequiredService<IMemoryCache>()));
```

## Blazor vs React 对比

| 特性 | Blazor Server | React |
|------|:------------:|:-----:|
| 开发语言 | C# | TypeScript/JS |
| 运行方式 | WebSocket 实时同步 | 浏览器执行 JS |
| SEO 友好 | 良好（SSR） | 需要 Next.js |
| .NET 原生集成 | 直接调用 | 需要 API |
| 组件库 | MASA Blazor / MudBlazor | MUI / Ant Design |
| 实时通信 | 天然支持 | 需要额外集成 |
| 单元测试 | bUnit | React Testing Library |
| 社区生态 | 快速成长 | 非常成熟 |

## 生产部署

### Nginx WebSocket 反向代理

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass         http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400s;
    }
}
```

### Docker 多阶段构建

```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app
EXPOSE 80

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["Blazor-Blog-Web.csproj", "."]
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app/publish --no-restore

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "Blazor-Blog-Web.dll"]
```

## 总结

Blazor 对于 .NET 开发者来说是一个极具吸引力的选择，特别是在团队已有 C# 技术积累的情况下。MASA Blazor 提供了丰富的 Material Design 组件，让 UI 开发效率大幅提升。通过合理运用组件通信、状态服务、表单验证和虚拟化列表等技术，完全可以构建出功能完整、体验流畅的现代化 Web 应用。

> 源码地址：[github.com/witeem/Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web)