---
title: "React + TypeScript 最佳实践：从 Hooks 到状态管理"
date: 2026-02-05
draft: false
tags: ["react", "typescript", "frontend", "hooks", "state-management"]
categories: ["前端开发", "React"]
description: "分享在 React Native 跨平台应用开发中总结的 TypeScript 最佳实践、自定义 Hooks 设计模式与状态管理方案"
---

## 前言

作为一名 .NET 后端转全栈的开发者，React 是我最常用的前端框架之一。本文结合 [rn-app](https://github.com/witeem/rn-app)（React Native 跨平台应用）和 [ssq-predictor](https://github.com/witeem/ssq-predictor)（React + TypeScript + Tauri 桌面应用）的实战经验，总结一些最佳实践。

## 1. TypeScript 类型定义规范

### API 响应类型

```typescript
// types/api.ts
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  timestamp: number;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

// 使用泛型
type PostListResponse = ApiResponse<PagedResult<Post>>;
```

### 组件 Props 类型

```typescript
// ✅ 推荐：使用 interface 定义 Props
interface ButtonProps {
  label: string;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
}

const Button: React.FC<ButtonProps> = ({
  label,
  variant = 'primary',
  disabled = false,
  loading = false,
  onClick
}) => {
  return (
    <button
      className={`btn btn-${variant}`}
      disabled={disabled || loading}
      onClick={onClick}
    >
      {loading ? <Spinner /> : label}
    </button>
  );
};
```

## 2. 自定义 Hooks 设计模式

### 数据获取 Hook

```typescript
// hooks/useFetch.ts
import { useState, useEffect, useCallback } from 'react';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

export function useFetch<T>(
  fetchFn: () => Promise<T>,
  deps: React.DependencyList = []
) {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const execute = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetchFn();
      setState({ data, loading: false, error: null });
    } catch (error) {
      setState({ data: null, loading: false, error: error as Error });
    }
  }, deps);

  useEffect(() => {
    execute();
  }, [execute]);

  return { ...state, refetch: execute };
}

// 使用
const { data: posts, loading, error, refetch } = useFetch(
  () => postApi.getAll(),
  []
);
```

### 本地存储 Hook

```typescript
// hooks/useLocalStorage.ts
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setValue = (value: T | ((val: T) => T)) => {
    try {
      const valueToStore = value instanceof Function
        ? value(storedValue)
        : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(error);
    }
  };

  return [storedValue, setValue] as const;
}
```

## 3. 状态管理方案选择

### 小型应用：Context + useReducer

```typescript
// store/postStore.tsx
type Action =
  | { type: 'SET_POSTS'; payload: Post[] }
  | { type: 'ADD_POST'; payload: Post }
  | { type: 'DELETE_POST'; payload: number };

interface State {
  posts: Post[];
  loading: boolean;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_POSTS':
      return { ...state, posts: action.payload, loading: false };
    case 'ADD_POST':
      return { ...state, posts: [action.payload, ...state.posts] };
    case 'DELETE_POST':
      return {
        ...state,
        posts: state.posts.filter(p => p.id !== action.payload)
      };
    default:
      return state;
  }
}

export const PostContext = createContext<{
  state: State;
  dispatch: React.Dispatch<Action>;
} | null>(null);
```

### 中大型应用：Zustand

```typescript
// store/usePostStore.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface PostStore {
  posts: Post[];
  loading: boolean;
  fetchPosts: () => Promise<void>;
  addPost: (post: Post) => void;
  deletePost: (id: number) => void;
}

export const usePostStore = create<PostStore>()(
  devtools(
    persist(
      (set) => ({
        posts: [],
        loading: false,
        fetchPosts: async () => {
          set({ loading: true });
          const posts = await postApi.getAll();
          set({ posts, loading: false });
        },
        addPost: (post) => set(state => ({
          posts: [post, ...state.posts]
        })),
        deletePost: (id) => set(state => ({
          posts: state.posts.filter(p => p.id !== id)
        })),
      }),
      { name: 'post-store' }
    )
  )
);
```

## 4. React Native 跨平台注意事项

在 [rn-app](https://github.com/witeem/rn-app) 中，以下几点值得注意：

```typescript
// 平台适配
import { Platform, StyleSheet } from 'react-native';

const styles = StyleSheet.create({
  container: {
    paddingTop: Platform.OS === 'ios' ? 44 : 24, // 状态栏高度
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 4 },
    }),
  },
});
```

## 总结

| 方案 | 适用场景 | 复杂度 |
|------|---------|--------|
| useState + Props | 组件内部状态 | ⭐ |
| Context + useReducer | 简单全局状态 | ⭐⭐ |
| Zustand | 中型应用 | ⭐⭐⭐ |
| Redux Toolkit | 大型复杂应用 | ⭐⭐⭐⭐ |

TypeScript + React 的组合极大地提升了代码的可维护性和重构信心。从 .NET 转过来的开发者会发现，TypeScript 的类型系统与 C# 有很多相似之处，上手非常顺畅。
