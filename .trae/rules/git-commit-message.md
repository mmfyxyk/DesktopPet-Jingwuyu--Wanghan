---
alwaysApply: true
scene: git_message
---

\#（在此处编写规则，自定义 AI 生成提交信息的风格。）

# Git Commit 提交信息生成规则（Conventional Commits 规范）

严格遵循 Angular 提交规范格式：
`<type>(<scope>): <简短标题，50字符以内，中文，动词开头，不句号>`

类型type只能从下面选取：

- feat：新增功能
- fix：bug修复
- perf：性能优化
- refactor：代码重构，无功能改动
- docs：文档修改
- style：格式、空格、分号，逻辑不变
- test：新增/修改测试用例
- chore：构建脚本、依赖、gitignore等杂项

scope填写模块名，例如 crawler、ui、resources、worker。

标题之后换行，输出简短变更清单：

- **每一条变更条目优先带上对应 type(scope):，不要只写纯描述**：***正确格式应为`<type>(<scope>):<描述>`***，示例：
fix(ui): 修复xxx问题
feat(scripts): 新增xxx脚本

- ***重复***：每一条变更条目优先带上对应 type(scope):，不要只写纯描述，应先写type(scope):，再写描述。
- 每一条描述本次做了什么改动，言简意赅，中文，不要大段复制代码
- 只写真正改动的文件对应的功能，不要编造不存在的改动
- 不要输出英文长段，不要粘贴堆栈、日志、完整代码

约束：

1. 标题行必须优先，第一行严格格式；
2. 不要多余前言、解释，直接输出commit消息本体；
3. 禁止输出markdown标题、\`\`\`代码块；
4. 变更条目不要太长，每条尽量控制在一行；
5. 如果改动跨多个模块，多个scope用逗号隔开，如 feat(crawler,ui): xxx
6. 尽可能依据diff内容区分每个子改动的type，如修复bug使用fix，性能优化使用perf，新增功能使用feat，构建脚本使用chore。

