------

title: "Blazor Server 实战：使用 MASA Blazor 构建现代化博客"title: "Blazor Server 实战：使用 MASA Blazor 构建现代化博客"

date: 2026-03-05date: 2026-03-05

draft: falsedraft: false

tags: ["blazor", "csharp", "dotnet", "frontend", "masa-blazor"]tags: ["blazor", "csharp", "dotnet", "frontend", "masa-blazor"]

categories: ["前端开发", "Blazor"]categories: ["前端开发", "Blazor"]

description: "从零开始用 Blazor Server + MASA Blazor 构建个人博客前端，涵盖组件通信、状态管理、表单验证、性能优化与生产部署完整实践"description: "从零开始用 Blazor Server + MASA Blazor 构建个人博客前端，涵盖组件开发、状态管理与服务集成"

------



## 为什么选择 Blazor？## 为什么选择 Blazor？



作为一名 .NET 开发者，Blazor 让我可以用熟悉的 C# 语言开发现代化的 Web 前端。相比 React/Vue，它能共享后端的数据模型和业务逻辑代码，减少重复劳动。作为一名 .NET 开发者，Blazor 让我可以用熟悉的 C# 语言开发现代化的 Web 前端。相比 React/Vue，它能共享后端的数据模型和业务逻辑代码，减少重复劳动。



[Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web) 是我基于 Blazor Server 开发的博客前端项目，UI 组件库采用了 MASA Blazor——一个基于 Material Design 规范、风格现代的 Blazor 组件库。[Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web) 是我基于 Blazor Server 开发的博客前端项目，UI 组件库采用了 MASA Blazor——一个基于 Material Design 规范、风格现代的 Blazor 组件库。



## 项目初始化## 项目初始化



```bash```bash

# 创建 Blazor Server 项目# 创建 Blazor Server 项目

dotnet new blazorserver -n Blazor-Blog-Webdotnet new blazorserver -n Blazor-Blog-Web



# 添加 MASA Blazor# 添加 MASA Blazor

dotnet add package Masa.Blazordotnet add package Masa.Blazor

``````



在 `Program.cs` 中注册服务：在 `Program.cs` 中注册服务：



```csharp```csharp

builder.Services.AddMasaBlazor(options =>builder.Services.AddMasaBlazor(options =>

{{

    options.ConfigureTheme(theme =>    options.ConfigureTheme(theme =>

    {    {

        theme.Themes.Light.Primary   = "#0084FF"; // 知乎蓝        theme.Themes.Light.Primary = "#6366f1"; // 自定义主色

        theme.Themes.Light.Secondary = "#00AAFF";    });

        theme.Themes.Dark.Primary    = "#66B5FF";});

    });```

});

```## 核心页面结构



## 核心页面结构### 主布局 MainLayout.razor



### 主布局 MainLayout.razor```razor

@inherits LayoutComponentBase

```razor

@inherits LayoutComponentBase<MApp>

    <MNavigationDrawer App Clipped>

<MApp>        <BlogSidebar />

    <MNavigationDrawer App Clipped @bind-Value="drawerOpen">    </MNavigationDrawer>

        <BlogSidebar />

    </MNavigationDrawer>    <MAppBar App Clipped Dense Elevation="1">

        <MAppBarNavIcon OnClick="ToggleDrawer" />

    <MAppBar App Clipped Dense Elevation="1">        <MToolbarTitle>Witeem's Blog</MToolbarTitle>

        <MAppBarNavIcon OnClick="@(() => drawerOpen = !drawerOpen)" />        <MSpacer />

        <MToolbarTitle>Witeem's Blog</MToolbarTitle>        <MButton Href="/about" Text>关于我</MButton>

        <MSpacer />    </MAppBar>

        <MButton Href="/posts" Text>文章</MButton>

        <MButton Href="/tags"  Text>标签</MButton>    <MMain>

        <MButton Href="/about" Text>关于我</MButton>        <MContainer MaxWidth="MaxWidth.Large">

    </MAppBar>            @Body

        </MContainer>

    <MMain>    </MMain>

        <MContainer MaxWidth="MaxWidth.Large"></MApp>

            @Body```

        </MContainer>

    </MMain>### 文章列表组件



    <MFooter App>```razor

        <span>© 2026 Witeem's Blog · Built with Blazor + MASA Blazor</span>@page "/posts"

    </MFooter>@inject IPostService PostService

</MApp>

<MRow>

@code {    @foreach (var post in posts)

    private bool drawerOpen = true;    {

}        <MCol Cols="12" Md="4">

```            <MCard Hover>

                <MCardTitle>@post.Title</MCardTitle>

### 文章列表组件                <MCardSubtitle>@post.CreatedAt.ToString("yyyy-MM-dd")</MCardSubtitle>

                <MCardText>@post.Summary</MCardText>

```razor                <MCardActions>

@page "/posts"                    <MButton Text Color="primary" Href="@($"/posts/{post.Slug}")">

@inject IPostService PostService                        阅读更多 →

                    </MButton>

@if (loading)                </MCardActions>

{            </MCard>

    <div class="d-flex justify-center mt-8">        </MCol>

        <MProgressCircular Indeterminate Color="primary" Size="48" />    }

    </div></MRow>

}

else@code {

{    private List<PostDto> posts = new();

    <MRow>

        @foreach (var post in posts)    protected override async Task OnInitializedAsync()

        {    {

            <MCol Cols="12" Md="4">        posts = await PostService.GetPostsAsync();

                <MCard Hover Class="mb-4" Elevation="2">    }

                    <MCardTitle>@post.Title</MCardTitle>}

                    <MCardSubtitle>```

                        <MIcon Small Class="mr-1">mdi-calendar</MIcon>

                        @post.CreatedAt.ToString("yyyy-MM-dd")## 状态管理

                        <MIcon Small Class="mx-1">mdi-eye</MIcon>

                        @post.ViewCountBlazor Server 的状态天然保持在服务器端，通过注入 Scoped 服务来共享状态：

                    </MCardSubtitle>

                    <MCardText>@post.Summary</MCardText>```csharp

                    <MCardActions>// 用户状态服务

                        @foreach (var tag in post.Tags.Take(3))public class UserStateService

                        {{

                            <MChip Small Color="primary" Outlined Class="mr-1">@tag</MChip>    public bool IsAuthenticated { get; private set; }

                        }    public string? UserName { get; private set; }

                        <MSpacer />

                        <MButton Text Color="primary" Href="@($"/posts/{post.Slug}")">    public event Action? OnChange;

                            阅读更多 →

                        </MButton>    public void Login(string userName)

                    </MCardActions>    {

                </MCard>        IsAuthenticated = true;

            </MCol>        UserName = userName;

        }        NotifyStateChanged();

    </MRow>    }

}

    private void NotifyStateChanged() => OnChange?.Invoke();

@code {}

    private List<PostDto> posts = new();```

    private bool loading = true;

```razor

    protected override async Task OnInitializedAsync()@inject UserStateService UserState

    {@implements IDisposable

        posts = await PostService.GetPostsAsync();

        loading = false;@if (UserState.IsAuthenticated)

    }{

}    <span>欢迎，@UserState.UserName</span>

```}



## 组件通信模式@code {

    protected override void OnInitialized()

### 1. EventCallback — 父子通信    {

        UserState.OnChange += StateHasChanged;

```razor    }

<!-- 子组件 SearchBar.razor -->

<MTextField @bind-Value="keyword"    public void Dispose()

            Placeholder="搜索文章..."    {

            Clearable        UserState.OnChange -= StateHasChanged;

            PrependInnerIcon="mdi-magnify"    }

            OnKeyUp="OnKeyUp" />}

```

@code {

    [Parameter] public EventCallback<string> OnSearch { get; set; }## Blazor vs React 对比

    private string keyword = string.Empty;

| 特性 | Blazor Server | React |

    private async Task OnKeyUp(KeyboardEventArgs e)|------|--------------|-------|

    {| 语言 | C# | JavaScript/TypeScript |

        if (e.Key == "Enter")| 运行方式 | WebSocket 实时同步 | 浏览器执行 JS |

            await OnSearch.InvokeAsync(keyword);| SEO | 良好（SSR） | 需要 Next.js 等 |

    }| 首屏速度 | 较慢（需建立 WS 连接） | 较快 |

}| .NET 集成 | 原生 ✅ | 需要 API 调用 |

| 生态 | 成长中 | 非常成熟 |

<!-- 父组件调用 -->

<SearchBar OnSearch="HandleSearch" />## 总结



@code {Blazor 对于 .NET 开发者来说是一个极具吸引力的选择，特别是在团队已有 C# 技术积累的情况下。MASA Blazor 提供了丰富的 Material Design 组件，让 UI 开发效率大幅提升。

    private async Task HandleSearch(string keyword)

    {> 源码地址：[github.com/witeem/Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web)

        posts = await PostService.SearchAsync(keyword);
    }
}
```

### 2. CascadingValue — 跨层数据传递

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

MASA Blazor 与 Blazor 内置的 `EditForm` + DataAnnotations 无缝配合：

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
        <MTextField Label="姓名"
                    @bind-Value="form.Name"
                    For="@(() => form.Name)"
                    Outlined />

        <MTextField Label="邮箱"
                    @bind-Value="form.Email"
                    For="@(() => form.Email)"
                    Outlined Type="email" />

        <MTextarea Label="留言内容"
                   @bind-Value="form.Message"
                   For="@(() => form.Message)"
                   Outlined Rows="5" />

        <MButton Type="submit" Color="primary" Loading="@submitting" Block>
            发送留言
        </MButton>
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

千条数据只渲染可视区域内的元素，DOM 节点数恒定：

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

    // 只有 posts 数量真正变化时才触发 DOM diff
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
// Services/CachedPostService.cs
public class CachedPostService(IPostService inner, IMemoryCache cache) : IPostService
{
    public async Task<List<PostDto>> GetPostsAsync()
        => await cache.GetOrCreateAsync("posts:all", async entry =>
        {
            entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            return await inner.GetPostsAsync();
        }) ?? [];
}

// Program.cs 注册装饰器
builder.Services.AddScoped<PostService>();
builder.Services.AddScoped<IPostService>(sp =>
    new CachedPostService(
        sp.GetRequiredService<PostService>(),
        sp.GetRequiredService<IMemoryCache>()));
```

### 4. 懒加载图片

```razor
<img src="@post.CoverUrl"
     loading="lazy"
     alt="@post.Title"
     style="width:100%;border-radius:8px" />
```

## Blazor vs React 对比

| 特性 | Blazor Server | React |
|------|:------------:|:-----:|
| 开发语言 | C# | TypeScript/JS |
| 运行方式 | WebSocket 实时同步 | 浏览器执行 JS |
| SEO 友好 | ✅（SSR） | 需要 Next.js |
| 首屏速度 | ⚡ 较慢（建立 WS） | ⚡⚡ 较快 |
| .NET 原生集成 | ✅ 直接调用 | ❌ 需要 API |
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
        # Blazor Server 必须开启 WebSocket 升级
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400s;   # 长连接，防止断开
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

> ⚠️ **注意**：Blazor Server 依赖持久的 WebSocket 连接，大量并发用户时服务端内存压力较大。如果用户体量上万，建议评估迁移到 **Blazor WebAssembly** 或 **Blazor United（.NET 8 Auto 模式）** 以分散压力。

## 总结

Blazor 对于 .NET 开发者来说是一个极具吸引力的选择，特别是在团队已有 C# 技术积累的情况下。MASA Blazor 提供了丰富的 Material Design 组件，让 UI 开发效率大幅提升。通过合理运用组件通信、状态服务、表单验证和虚拟化列表等技术，完全可以构建出功能完整、体验流畅的现代化 Web 应用。

> 源码地址：[github.com/witeem/Blazor-Blog-Web](https://github.com/witeem/Blazor-Blog-Web)
