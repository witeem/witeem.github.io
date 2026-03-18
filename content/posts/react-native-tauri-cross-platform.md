---
title: "React Native + Tauri 跨平台开发实践"
date: 2026-01-01
draft: false
tags: ["react", "typescript", "tauri", "rust", "cross-platform", "desktop", "mobile"]
categories: ["跨平台开发"]
description: "深入对比 React Native 移动端与 Tauri 桌面端两种跨平台方案，涵盖性能优化、原生模块调用、动画、热更新与发布流程"
---

## 前言

跨平台开发一直是技术选型的难点。本文结合两个实际项目：

- **[rn-app](https://github.com/witeem/rn-app)**：React Native 跨平台移动应用（iOS + Android + Web）
- **[ssq-predictor](https://github.com/witeem/ssq-predictor)**：React + TypeScript + Tauri 桌面应用

分享两种截然不同的跨平台方案，帮助你在技术选型时做出更明智的决策。

## 方案一：React Native（移动端）

### 项目结构

```
rn-app/
├── src/
│   ├── components/     # 通用组件（Button、Input、Card...）
│   ├── screens/        # 页面组件
│   ├── navigation/     # React Navigation 导航配置
│   ├── store/          # Zustand / Redux 状态管理
│   ├── services/       # API 封装
│   ├── hooks/          # 自定义 Hooks
│   └── utils/          # 工具函数
├── android/            # Android 原生代码
├── ios/                # iOS 原生代码
└── package.json
```

### 导航系统（React Navigation v7）

```typescript
// navigation/AppNavigator.tsx
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

type RootStackParamList = {
  Home:    undefined;
  Detail:  { id: number; title: string };
  Profile: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab   = createBottomTabNavigator();

function HomeTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          const icon = route.name === 'Feed'
            ? (focused ? 'home'   : 'home-outline')
            : (focused ? 'person' : 'person-outline');
          return <Ionicons name={icon} size={size} color={color} />;
        },
        tabBarActiveTintColor: '#0084FF',
      })}
    >
      <Tab.Screen name="Feed"    component={FeedScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Home"   component={HomeTabs} options={{ headerShown: false }} />
        <Stack.Screen name="Detail" component={DetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

### 网络请求封装（拦截器 + 自动刷新 Token）

```typescript
// services/httpClient.ts
import axios, { AxiosInstance } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

class HttpClient {
  private instance: AxiosInstance;
  private isRefreshing = false;
  private failedQueue: Array<{ resolve: Function; reject: Function }> = [];

  constructor() {
    this.instance = axios.create({
      baseURL: process.env.API_URL,
      timeout: 10000,
    });
    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.instance.interceptors.request.use(async config => {
      const token = await AsyncStorage.getItem('access_token');
      if (token) config.headers.Authorization = `Bearer ${token}`;
      return config;
    });

    this.instance.interceptors.response.use(
      res => res.data,
      async error => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.isRefreshing) {
            // 等待 Token 刷新完成后重放请求
            return new Promise((resolve, reject) => {
              this.failedQueue.push({ resolve, reject });
            }).then(token => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              return this.instance(originalRequest);
            });
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            const refreshToken = await AsyncStorage.getItem('refresh_token');
            const { data } = await axios.post('/auth/refresh', { refreshToken });
            await AsyncStorage.setItem('access_token', data.accessToken);
            this.failedQueue.forEach(p => p.resolve(data.accessToken));
            this.failedQueue = [];
            return this.instance(originalRequest);
          } catch {
            this.failedQueue.forEach(p => p.reject(error));
            await AsyncStorage.multiRemove(['access_token', 'refresh_token']);
          } finally {
            this.isRefreshing = false;
          }
        }
        return Promise.reject(error);
      }
    );
  }

  get<T>(url: string)               { return this.instance.get<never, T>(url); }
  post<T>(url: string, data: unknown) { return this.instance.post<never, T>(url, data); }
}

export const http = new HttpClient();
```

### 性能优化

```typescript
// 1. 使用 FlashList 替代 FlatList（速度快 10 倍）
import { FlashList } from '@shopify/flash-list';

<FlashList
  data={posts}
  estimatedItemSize={120}
  renderItem={({ item }) => <PostCard post={item} />}
  keyExtractor={item => String(item.id)}
/>

// 2. 图片缓存（react-native-fast-image）
import FastImage from 'react-native-fast-image';

<FastImage
  source={{ uri: post.coverUrl, priority: FastImage.priority.normal }}
  style={{ width: '100%', height: 200 }}
  resizeMode={FastImage.resizeMode.cover}
/>

// 3. memo + useCallback 防止子组件不必要重渲染
const PostCard = React.memo(({ post, onPress }: PostCardProps) => (
  <TouchableOpacity onPress={() => onPress(post.id)}>
    <Text>{post.title}</Text>
  </TouchableOpacity>
));
```

### 动画（Reanimated 3）

```typescript
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

function LikeButton({ onLike }: { onLike: () => void }) {
  const scale = useSharedValue(1);
  const color = useSharedValue(0); // 0: grey, 1: red

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: withTiming(color.value === 1 ? 1 : 0.6),
  }));

  const handlePress = () => {
    scale.value = withSpring(1.4, {}, () => {
      scale.value = withSpring(1);
    });
    color.value = color.value === 0 ? 1 : 0;
    onLike();
  };

  return (
    <Animated.View style={animStyle}>
      <TouchableOpacity onPress={handlePress}>
        <Icon name="heart" size={24} />
      </TouchableOpacity>
    </Animated.View>
  );
}
```

## 方案二：Tauri + React（桌面端）

Tauri 是 Rust 编写的桌面应用框架，前端用任意 Web 技术。相比 Electron：
- 打包体积：~5MB vs ~100MB+
- 内存占用：低 60% 以上
- 启动速度：快 2–5 倍

### 项目结构

```
ssq-predictor/
├── src/                  # React 前端
│   ├── components/
│   ├── hooks/
│   └── utils/
├── src-tauri/            # Rust 后端
│   ├── src/
│   │   ├── main.rs       # 入口
│   │   └── predictor.rs  # 预测算法
│   └── tauri.conf.json
└── package.json
```

### Rust 命令定义

```rust
// src-tauri/src/predictor.rs
use std::collections::HashMap;
use tauri::command;

#[command]
pub fn predict_numbers(history: Vec<Vec<u32>>) -> Vec<u32> {
    let mut frequency: HashMap<u32, u32> = HashMap::new();

    for draw in &history {
        for &num in draw {
            *frequency.entry(num).or_insert(0) += 1;
        }
    }

    let mut sorted: Vec<(u32, u32)> = frequency.into_iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(&a.1));

    sorted.iter().take(7).map(|(num, _)| *num).collect()
}

// 文件读写（访问本地文件系统，这是 Electron 很容易做到的事，Tauri 也一样）
#[command]
pub async fn save_history(history: Vec<Vec<u32>>, path: String) -> Result<(), String> {
    let json = serde_json::to_string(&history).map_err(|e| e.to_string())?;
    tokio::fs::write(&path, json).await.map_err(|e| e.to_string())
}

// src-tauri/src/main.rs
fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            predictor::predict_numbers,
            predictor::save_history,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### React 调用 Rust 命令

```typescript
// hooks/usePredictor.ts
import { invoke } from '@tauri-apps/api/core';
import { save }   from '@tauri-apps/plugin-dialog';

export function usePredictor() {
  const [prediction, setPrediction] = useState<number[]>([]);
  const [loading,    setLoading]    = useState(false);

  const predict = async (history: number[][]) => {
    setLoading(true);
    try {
      const result = await invoke<number[]>('predict_numbers', { history });
      setPrediction(result);
    } catch (err) {
      console.error('预测失败:', err);
    } finally {
      setLoading(false);
    }
  };

  const exportHistory = async (history: number[][]) => {
    const filePath = await save({
      filters: [{ name: 'JSON', extensions: ['json'] }],
    });
    if (filePath) {
      await invoke('save_history', { history, path: filePath });
    }
  };

  return { prediction, loading, predict, exportHistory };
}
```

### Tauri 权限配置（v2）

```json
// src-tauri/capabilities/default.json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "ssq-predictor 默认权限",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "dialog:allow-save",
    "fs:allow-write-text-file",
    "fs:allow-read-text-file"
  ]
}
```

## 发布流程对比

### React Native — EAS Build（Expo Application Services）

```bash
# 安装 EAS CLI
npm install -g eas-cli

# 初始化
eas init

# eas.json 配置
{
  "build": {
    "production": {
      "android": { "buildType": "apk" },
      "ios":     { "simulator": false }
    }
  }
}

# 构建 Android APK
eas build --platform android --profile production

# 提交 App Store
eas submit --platform ios
```

### Tauri — GitHub Actions 自动发布

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ['v*']

jobs:
  publish-tauri:
    permissions:
      contents: write
    strategy:
      matrix:
        os: [ubuntu-22.04, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - uses: dtolnay/rust-toolchain@stable

      - name: Install dependencies (Ubuntu)
        if: matrix.os == 'ubuntu-22.04'
        run: |
          sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev

      - uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'Release ${{ github.ref_name }}'
```

## 方案对比

| 特性 | React Native | Tauri + React |
|------|:-----------:|:-------------:|
| 目标平台 | iOS / Android / Web | Windows / macOS / Linux |
| 开发语言 | TypeScript | TypeScript + Rust |
| 打包大小 | ~20MB（Android） | ~5MB |
| 内存占用 | 中等 | 低（接近原生） |
| 性能 | 良好 | 接近原生 |
| 热更新 | ✅（OTA 更新） | ❌（需重新打包） |
| 原生 API | 丰富（社区插件） | 通过 Rust 插件扩展 |
| 学习曲线 | 中等 | 需要了解 Rust |
| 生态成熟度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 适合团队 | 移动端为主 | 桌面工具类应用 |

## 总结

- **移动端**：React Native（搭配 Expo）依然是 TypeScript 开发者构建 iOS/Android 应用的最成熟选择，生态完善，社区活跃
- **桌面端**：Tauri 是 Electron 的强力替代品，体积小、性能高。如果你愿意学一点 Rust，回报是显著的

> 源码地址：
> - [github.com/witeem/rn-app](https://github.com/witeem/rn-app)
> - [github.com/witeem/ssq-predictor](https://github.com/witeem/ssq-predictor)
