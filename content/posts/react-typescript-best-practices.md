---
title: "React + TypeScript 最佳实践：从 Hooks 到状态管理"
date: 2026-02-05
draft: false
tags: ["react", "typescript", "frontend", "hooks", "state-management", "performance"]
categories: ["前端开发", "React"]
description: "深入总结 React + TypeScript 工程化最佳实践，涵盖类型定义规范、自定义 Hooks 设计、状态管理选型、性能优化、错误边界与组件测试"
---

## 前言

作为一名 .NET 后端转全栈的开发者，React 是我最常用的前端框架之一。本文结合 [rn-app](https://github.com/witeem/rn-app)（React Native 跨平台应用）和 [ssq-predictor](https://github.com/witeem/ssq-predictor)（React + TypeScript + Tauri 桌面应用）的实战经验，总结一套可直接落地的最佳实践。

## 1. TypeScript 类型定义规范

### API 响应通用类型

```typescript
// types/api.ts
export interface ApiResponse<T> {
  code:      number;
  message:   string;
  data:      T;
  timestamp: number;
}

export interface PagedResult<T> {
  items:    T[];
  total:    number;
  page:     number;
  pageSize: number;
}

// 复合类型，减少重复书写
type PostListResponse = ApiResponse<PagedResult<Post>>;
```

### 组件 Props 类型规范

```typescript
// ✅ 推荐：interface 定义 Props，属性顺序：必须 → 可选 → 回调
interface ButtonProps {
  // 必须属性
  label:    string;
  // 可选属性
  variant?: 'primary' | 'secondary' | 'danger';
  size?:    'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?:  boolean;
  // 事件回调
  onClick?:  (event: React.MouseEvent<HTMLButtonElement>) => void;
}

const Button: React.FC<ButtonProps> = ({
  label,
  variant  = 'primary',
  size     = 'md',
  disabled = false,
  loading  = false,
  onClick,
}) => (
  <button
    className={`btn btn-${variant} btn-${size}`}
    disabled={disabled || loading}
    onClick={onClick}
  >
    {loading ? <Spinner size={16} /> : label}
  </button>
);

// ✅ 使用 ComponentPropsWithoutRef 扩展原生属性
interface InputProps extends React.ComponentPropsWithoutRef<'input'> {
  label:    string;
  error?:   string;
  hint?:    string;
}
```

### 严格区分 Type 与 Interface

```typescript
// interface：优先用于对象形状，支持 extends 和 declaration merging
interface User {
  id:       number;
  name:     string;
  email:    string;
}

interface AdminUser extends User {
  permissions: string[];
}

// type：用于联合类型、交叉类型、工具类型
type Status  = 'pending' | 'active' | 'suspended';
type UserOrAdmin = User | AdminUser;
type ReadonlyUser = Readonly<User>;
type PartialUser  = Partial<User>;
type UserDto      = Pick<User, 'id' | 'name'>;
```

## 2. 自定义 Hooks 设计模式

### 数据获取 Hook（含竞态处理）

```typescript
// hooks/useFetch.ts
import { useState, useEffect, useCallback, useRef } from 'react';

interface FetchState<T> {
  data:    T | null;
  loading: boolean;
  error:   Error | null;
}

export function useFetch<T>(
  fetchFn: () => Promise<T>,
  deps: React.DependencyList = []
) {
  const [state, setState] = useState<FetchState<T>>({
    data: null, loading: true, error: null,
  });

  // 用 ref 标记是否已卸载，防止竞态条件下的 setState 报错
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const execute = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetchFn();
      if (mountedRef.current) setState({ data, loading: false, error: null });
    } catch (err) {
      if (mountedRef.current)
        setState({ data: null, loading: false, error: err as Error });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { execute(); }, [execute]);

  return { ...state, refetch: execute };
}

// 用法
const { data: posts, loading, error, refetch } = useFetch(
  () => postApi.getAll(), []
);
```

### 防抖 Hook

```typescript
// hooks/useDebounce.ts
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// 搜索场景
function SearchBar() {
  const [keyword, setKeyword] = useState('');
  const debouncedKeyword = useDebounce(keyword, 400);

  useEffect(() => {
    if (debouncedKeyword) search(debouncedKeyword);
  }, [debouncedKeyword]);

  return <input value={keyword} onChange={e => setKeyword(e.target.value)} />;
}
```

### 本地存储 Hook（类型安全）

```typescript
// hooks/useLocalStorage.ts
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setValue = useCallback((value: T | ((val: T) => T)) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(`useLocalStorage [${key}] write error:`, error);
    }
  }, [key, storedValue]);

  const removeValue = useCallback(() => {
    setStoredValue(initialValue);
    window.localStorage.removeItem(key);
  }, [key, initialValue]);

  return [storedValue, setValue, removeValue] as const;
}
```

## 3. 状态管理方案选型

### 小型应用：Context + useReducer

```typescript
// store/postStore.tsx
type Action =
  | { type: 'SET_POSTS';   payload: Post[] }
  | { type: 'ADD_POST';    payload: Post }
  | { type: 'DELETE_POST'; payload: number }
  | { type: 'SET_LOADING'; payload: boolean };

interface State {
  posts:   Post[];
  loading: boolean;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_POSTS':   return { ...state, posts: action.payload, loading: false };
    case 'ADD_POST':    return { ...state, posts: [action.payload, ...state.posts] };
    case 'DELETE_POST': return { ...state, posts: state.posts.filter(p => p.id !== action.payload) };
    case 'SET_LOADING': return { ...state, loading: action.payload };
    default: return state;
  }
}

// Context + Provider
const PostContext = createContext<{
  state: State;
  dispatch: React.Dispatch<Action>;
} | null>(null);

export function PostProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { posts: [], loading: false });
  return <PostContext.Provider value={{ state, dispatch }}>{children}</PostContext.Provider>;
}

export const usePostStore = () => {
  const ctx = useContext(PostContext);
  if (!ctx) throw new Error('usePostStore must be used within PostProvider');
  return ctx;
};
```

### 中大型应用：Zustand（推荐）

```typescript
// store/usePostStore.ts
import { create } from 'zustand';
import { devtools, persist, subscribeWithSelector } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

interface PostStore {
  posts:      Post[];
  loading:    boolean;
  searchText: string;
  // Actions
  fetchPosts:    () => Promise<void>;
  addPost:       (post: Post) => void;
  deletePost:    (id: number) => void;
  setSearchText: (text: string) => void;
  // Computed（通过 selector 实现）
}

export const usePostStore = create<PostStore>()(
  devtools(
    persist(
      immer(set => ({
        posts:      [],
        loading:    false,
        searchText: '',

        fetchPosts: async () => {
          set(state => { state.loading = true; });
          const posts = await postApi.getAll();
          set(state => { state.posts = posts; state.loading = false; });
        },

        addPost: post => set(state => {
          state.posts.unshift(post); // immer 允许直接"修改"
        }),

        deletePost: id => set(state => {
          state.posts = state.posts.filter(p => p.id !== id);
        }),

        setSearchText: text => set(state => { state.searchText = text; }),
      })),
      { name: 'post-store', partialize: state => ({ posts: state.posts }) }
    )
  )
);

// Selector：细粒度订阅，防止不必要渲染
const filteredPosts = usePostStore(state =>
  state.posts.filter(p =>
    p.title.toLowerCase().includes(state.searchText.toLowerCase())
  )
);
```

### 状态管理选型建议

| 方案 | 适用场景 | 复杂度 | Bundle Size |
|------|---------|--------|------------|
| useState + Props | 组件内部状态 | ⭐ | 0 |
| Context + useReducer | 简单全局状态 | ⭐⭐ | 0 |
| Zustand | 中型应用 | ⭐⭐⭐ | ~3KB |
| Jotai | 原子化状态 | ⭐⭐⭐ | ~3KB |
| Redux Toolkit | 大型复杂应用 | ⭐⭐⭐⭐ | ~20KB |
| TanStack Query | 服务端状态管理 | ⭐⭐⭐ | ~12KB |

## 4. 性能优化

### memo + useCallback + useMemo 三件套

```typescript
// ❌ 每次父组件渲染，子组件都会重新渲染
function Parent() {
  const [count, setCount] = useState(0);
  const handleClick = () => console.log('clicked'); // 每次新建函数引用

  return <ExpensiveChild onAction={handleClick} />;
}

// ✅ 正确使用
function Parent() {
  const [count, setCount] = useState(0);
  const handleClick = useCallback(() => console.log('clicked'), []); // 稳定引用
  const expensiveValue = useMemo(() => computeExpensive(count), [count]); // 缓存计算

  return <ExpensiveChild onAction={handleClick} value={expensiveValue} />;
}

// 子组件用 memo 包裹
const ExpensiveChild = React.memo(({ onAction, value }: ChildProps) => {
  return <div onClick={onAction}>{value}</div>;
});
```

### 代码分割（React.lazy）

```typescript
// 路由级懒加载，减少首屏 Bundle
const PostList   = lazy(() => import('./pages/PostList'));
const PostDetail = lazy(() => import('./pages/PostDetail'));
const About      = lazy(() => import('./pages/About'));

function App() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/posts"     element={<PostList />} />
        <Route path="/posts/:id" element={<PostDetail />} />
        <Route path="/about"     element={<About />} />
      </Routes>
    </Suspense>
  );
}
```

## 5. 错误边界

```typescript
// components/ErrorBoundary.tsx
interface State { hasError: boolean; error: Error | null; }

class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  State
> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 上报错误到监控平台
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="error-page">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
          <button onClick={() => this.setState({ hasError: false, error: null })}>
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// 使用
<ErrorBoundary fallback={<ErrorFallback />}>
  <PostDetail id={id} />
</ErrorBoundary>
```

## 6. 组件测试（React Testing Library）

```typescript
// __tests__/Button.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '../Button';

describe('Button', () => {
  it('renders label correctly', () => {
    render(<Button label="提交" />);
    expect(screen.getByText('提交')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const handleClick = jest.fn();
    render(<Button label="点击" onClick={handleClick} />);
    fireEvent.click(screen.getByText('点击'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('shows spinner when loading', () => {
    render(<Button label="提交" loading />);
    expect(screen.getByRole('status')).toBeInTheDocument(); // Spinner
    expect(screen.queryByText('提交')).not.toBeInTheDocument();
  });

  it('is disabled when loading', () => {
    render(<Button label="提交" loading />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

## 7. React Native 平台适配

在 [rn-app](https://github.com/witeem/rn-app) 中，跨平台样式适配是常见问题：

```typescript
import { Platform, StyleSheet, StatusBar } from 'react-native';

const styles = StyleSheet.create({
  safeArea: {
    // iOS 状态栏高度通过 SafeAreaView 处理，Android 需要手动偏移
    paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0,
  },
  shadow: {
    // iOS 阴影
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.15,
        shadowRadius: 4,
      },
      // Android 高程阴影
      android: { elevation: 4 },
      // Web 使用 CSS box-shadow
      default: { boxShadow: '0 2px 8px rgba(0,0,0,0.15)' },
    }),
  },
});
```

## 总结

从 .NET 转前端，TypeScript 的类型系统与 C# 有很多相似之处，上手非常顺畅。结合这些最佳实践：

1. **类型先行**：先定义接口和类型，再写实现，避免 `any` 泛滥
2. **Hooks 复用**：将可复用的有状态逻辑提取为自定义 Hook
3. **按需选型**：不要过早引入复杂状态管理，Context 够用就不用 Redux
4. **性能意识**：`memo` / `useCallback` / `lazy` 三件套，按需使用而非滥用
5. **测试覆盖**：关键组件和 Hooks 必须有测试，TDD 提升重构信心
