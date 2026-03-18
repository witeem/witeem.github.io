---
title: "React Native + Tauri 跨平台开发实践"
date: 2026-01-01
draft: false
tags: ["react", "typescript", "tauri", "rust", "cross-platform", "desktop"]
categories: ["跨平台开发"]
description: "分享使用 React Native 构建移动应用与 Tauri + React 构建桌面应用的经验对比与实践总结"
---

## 前言

跨平台开发一直是技术选型的难点。本文结合两个实际项目：

- **[rn-app](https://github.com/witeem/rn-app)**：React Native 跨平台移动应用（iOS + Android + Web）
- **[ssq-predictor](https://github.com/witeem/ssq-predictor)**：React + TypeScript + Tauri 桌面应用

分享两种不同的跨平台方案选择。

## 方案一：React Native（移动端）

### 项目结构

```
rn-app/
├── src/
│   ├── components/     # 通用组件
│   ├── screens/        # 页面组件
│   ├── navigation/     # 导航配置
│   ├── store/          # 状态管理
│   ├── services/       # API 服务
│   └── hooks/          # 自定义 Hooks
├── android/            # Android 原生代码
├── ios/                # iOS 原生代码
└── package.json
```

### 导航系统（React Navigation）

```typescript
// navigation/AppNavigator.tsx
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

type RootStackParamList = {
  Home: undefined;
  Detail: { id: number; title: string };
  Profile: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator();

function HomeTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          const iconName = route.name === 'Feed'
            ? (focused ? 'home' : 'home-outline')
            : (focused ? 'person' : 'person-outline');
          return <Ionicons name={iconName} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="Feed" component={FeedScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Home" component={HomeTabs} options={{ headerShown: false }} />
        <Stack.Screen name="Detail" component={DetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

### 网络请求封装

```typescript
// services/httpClient.ts
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

class HttpClient {
  private instance: AxiosInstance;

  constructor() {
    this.instance = axios.create({
      baseURL: process.env.API_URL,
      timeout: 10000,
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    // 请求拦截：自动附加 Token
    this.instance.interceptors.request.use(async (config) => {
      const token = await AsyncStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // 响应拦截：统一错误处理
    this.instance.interceptors.response.use(
      (response) => response.data,
      async (error) => {
        if (error.response?.status === 401) {
          await AsyncStorage.removeItem('auth_token');
          // 跳转登录页
        }
        return Promise.reject(error);
      }
    );
  }

  get<T>(url: string, config?: AxiosRequestConfig) {
    return this.instance.get<never, T>(url, config);
  }

  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return this.instance.post<never, T>(url, data, config);
  }
}

export const http = new HttpClient();
```

## 方案二：Tauri + React（桌面端）

Tauri 是一个用 Rust 编写的桌面应用框架，前端使用任意 Web 技术（本项目用 React + TypeScript）。相比 Electron，Tauri 打包体积小 20 倍以上。

### 项目结构

```
ssq-predictor/
├── src/                # React 前端
│   ├── components/
│   ├── hooks/
│   └── utils/
├── src-tauri/          # Rust 后端
│   ├── src/
│   │   └── main.rs    # Tauri 命令
│   └── tauri.conf.json
└── package.json
```

### Rust 命令定义

```rust
// src-tauri/src/main.rs
use tauri::command;

#[command]
fn predict_numbers(history: Vec<Vec<u32>>) -> Vec<u32> {
    // 加权算法预测双色球号码
    let mut frequency: HashMap<u32, u32> = HashMap::new();

    for draw in &history {
        for &num in draw {
            *frequency.entry(num).or_insert(0) += 1;
        }
    }

    // 按频率排序，取前 6 个红球 + 1 个蓝球
    let mut sorted: Vec<(u32, u32)> = frequency.into_iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(&a.1));

    sorted.iter().take(7).map(|(num, _)| *num).collect()
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![predict_numbers])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### React 调用 Rust 命令

```typescript
// hooks/usePredictor.ts
import { invoke } from '@tauri-apps/api/tauri';

export function usePredictor() {
  const [prediction, setPrediction] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);

  const predict = async (history: number[][]) => {
    setLoading(true);
    try {
      const result = await invoke<number[]>('predict_numbers', { history });
      setPrediction(result);
    } catch (error) {
      console.error('预测失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return { prediction, loading, predict };
}
```

## 方案对比

| 特性 | React Native | Tauri + React |
|------|-------------|---------------|
| 目标平台 | iOS / Android / Web | Windows / macOS / Linux |
| 语言 | TypeScript / JS | TypeScript + Rust |
| 打包大小 | 较大 | 非常小（~5MB） |
| 性能 | 良好 | 接近原生 |
| 原生 API | 丰富 | 通过 Rust 扩展 |
| 学习曲线 | 中等 | 需要学 Rust |
| 生态 | 非常成熟 | 快速成长 |

## 总结

- **移动端**：React Native 依然是 TypeScript/JS 开发者的最佳选择
- **桌面端**：Tauri 是 Electron 的强力替代品，值得投入学习

> 源码地址：
> - [github.com/witeem/rn-app](https://github.com/witeem/rn-app)
> - [github.com/witeem/ssq-predictor](https://github.com/witeem/ssq-predictor)
