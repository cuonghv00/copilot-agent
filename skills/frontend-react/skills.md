---
name: frontend-react
description: Best practices for React, TypeScript, and Next.js frontend development.
license: MIT
---

# Frontend React Skill

## Quy ước Code
- Dùng **TypeScript** cho mọi file (`.ts`, `.tsx`), tuyệt đối không dùng `.js` / `.jsx`.
- Khai báo kiểu dữ liệu rõ ràng bằng `interface` (ưu tiên) hoặc `type` cho Props, State, và API responses.
- Viết **Functional Components** với React Hooks. Không dùng Class Components.
- Sử dụng Arrow Functions để khai báo Component: `const MyComponent: React.FC<Props> = ({ prop }) => { ... }`.
- Tên Component luôn là PascalCase (ví dụ: `UserProfile`). Tên biến, state, function là camelCase.

## Quản lý State & Side Effects
- Hạn chế sử dụng `useEffect` nếu có thể suy luận trực tiếp từ render cycle (Derived State).
- Dùng Custom Hooks để gom nhóm logic (ví dụ `useAuth`, `useFetchUser`) thay vì nhồi nhét logic vào trong UI Component.
- Tuyệt đối không mutate state trực tiếp. Luôn dùng function update (ví dụ: `setItems(prev => [...prev, newItem])`).

## Kiến trúc & Next.js
- Phân tách rõ ràng giữa **UI Components** (chỉ lo hiển thị, stateless) và **Container Components** (lo fetching data, xử lý logic).
- Nếu dùng Next.js (App Router): Chú ý phân biệt rõ ràng `"use client"` và Server Components.
- Mặc định là Server Component, chỉ thêm `"use client"` khi thực sự cần state, hooks, hoặc event listeners (`onClick`).

## CSS & Styling
- Ưu tiên sử dụng **Tailwind CSS**.
- Nếu dùng CSS Modules, tên class dùng camelCase (`styles.myButton`).
- Tránh viết inline styles trừ trường hợp style động thay đổi liên tục theo state.

## Output
- Trả về code đã hoàn thiện, không cắt xén trừ khi quá dài.
- Chỉ hiển thị nội dung file, không đưa ra bình luận thừa.
