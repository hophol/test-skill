---
name: fe-dev-design
description: 前端开发设计（技术方案）。当用户拿着需求或需求说明问"前端要怎么实现 / 如何实现 / 方案怎么出"，或需要产出技术实现方案——组件树与职责划分、状态管理、路由组织、API 对接约定、目录结构——时必须使用。只要意图是给出实现方案就用本 skill；若只是把 PRD/原型图整理成需求说明，那是 fe-req-analysis 的事。
allowed-tools: Read, Write, Grep, Glob
metadata:
  owner: lisi
  stage: dev
---

# 前端开发设计

把前端需求说明转化为可直接开工的技术方案。

## 流程

> 组件树骨架参照 `templates/component-tree.md` 模板起手


1. 读前端需求说明（没有就先建议走 fe-req-analysis 产出一份）
2. 组件树设计：容器 / 展示分层，标出可复用组件
3. 状态管理：local / global 划分，选型遵循项目现有约定（先读 package.json 判断技术栈）
4. API 对接：接口清单、请求时机、loading / error 处理位置
5. 路由与目录：新增路由、文件放置位置
6. 输出 `fe-dev-{功能名}.md`，章节固定为：组件树 / 状态设计 / API 对接 / 路由与目录 / 风险点

## 边界

- 不重写需求；发现需求不清，退回 fe-req-analysis
- 不写测试用例（那是 fe-test-design 的事）
